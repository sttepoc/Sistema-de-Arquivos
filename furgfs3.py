"""
FURGfs3 - Sistema de Arquivos em único arquivo (.fs)
Autor: Implementação para disciplina (gerado por ChatGPT)
Linguagem: Python 3.x
Dependências:
  - pandas

Como usar:
  1) pip install pandas
  2) python furgfs3.py          # roda exemplos / CLI mínima presente no final
  3) Importar a classe FURGfs3 em outros scripts se desejar.

O arquivo .fs contém:
  - Header (info do FS)
  - FAT (lista de inteiros por bloco)
  - Diretório (dicionário com entradas e metadados)
  - Área de dados (blocos fixos)

Detalhes de implementação:
  - Blocos de metadados ocupam um número inicial de blocos (reservados).
  - FAT e diretório são gravados com pickle nos blocos reservados.
  - FAT: cada entrada contém:
      0 => livre
     -1 => fim de cadeia
      n (>0) => índice do próximo bloco
  - Arquivos são armazenados por lista encadeada de blocos (como FAT tradicional).
  - Diretórios são hierárquicos; chaves são paths absolutos ("/", "/pasta/arquivo").
  - A proteção impede remoção/overwriting pelo método copy_in/rename/remove/etc.
"""

import os
import math
import pickle
import hashlib
import time
from datetime import datetime
import pandas as pd

# ---------------------------
# Utilitários
# ---------------------------

def sha256_bytes(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()

def now_ts() -> float:
    return time.time()

def human_size(nbytes: int) -> str:
    # formata bytes em MB/KB
    if nbytes >= 1024*1024:
        return f"{nbytes / (1024*1024):.2f} MB"
    if nbytes >= 1024:
        return f"{nbytes / 1024:.2f} KB"
    return f"{nbytes} B"

# ---------------------------
# Classe FURGfs3
# ---------------------------

class FURGfs3:
    def __init__(self, fs_path: str):
        """
        Inicializa manipulador do arquivo .fs (não cria automaticamente).
        Para criar, use create_fs(size_mb, block_size).
        """
        self.fs_path = fs_path
        self.mounted = False
        # estruturas em memória (serão carregadas com mount/load)
        self.header = None
        self.fat = None
        self.dir = None  # dicionário {path: metadata}
        self.current_dir = "/"  # diretório de trabalho dentro do FS

    # ---------------------------
    # Criação / formatação / persistência
    # ---------------------------

    def create_fs(self, size_mb: int, block_size: int = 4096, min_blocks_reserved=8):
        """
        Cria um novo sistema de arquivos no arquivo self.fs_path.
        size_mb: tamanho total em MB (inteiro)
        block_size: tamanho do bloco em bytes (padrão 4 KB)
        min_blocks_reserved: número mínimo de blocos reservados para metadados
        """
        if size_mb < 1:
            raise ValueError("Tamanho mínimo 1 MB.")
        total_bytes = size_mb * 1024 * 1024
        total_blocks = total_bytes // block_size
        if total_blocks < 32:
            raise ValueError("FS muito pequeno: aumente o tamanho ou diminua block_size.")
        # Reservar alguns blocos para header+fat+diretório
        # Estimativa: FAT precisa de total_blocks integers; cada int ~ 4-8 bytes pickled -> reserve ceil
        # Para simplicidade, reserve min_blocks_reserved ou 1% do total, o que for maior.
        reserved_blocks = max(min_blocks_reserved, math.ceil(total_blocks * 0.01))
        if reserved_blocks >= total_blocks // 2:
            reserved_blocks = max(8, total_blocks // 10)

        # Inicializar estruturas
        header = {
            "magic": b"FURGFS3",  # identificação
            "version": 1,
            "fs_bytes": total_bytes,
            "block_size": block_size,
            "total_blocks": total_blocks,
            "reserved_blocks": reserved_blocks,
            # endereços (em blocos)
            "addr_header": 0,
            "addr_fat": 1,
            "addr_dir": 1 + 1,  # simplificado: header occupies block 0; fat starts at 1, dir at next
            # We will actually store fat and dir within the reserved area; these fields are informative.
            "last_modified": now_ts()
        }

        # Inicial FAT: 0 = livre
        fat = [0] * total_blocks
        # marcar blocos reservados como ocupados na FAT (metadata area)
        for i in range(reserved_blocks):
            fat[i] = -1  # reservado/ocupado (terminador)
        # Diretório raiz
        root_meta = {
            "is_dir": True,
            "name": "/",
            "parent": None,
            "created": now_ts(),
            "modified": now_ts(),
            "protected": False,
            "blocks": [],  # diretórios podem ter metadados em si, mas aqui não armazenamos listagem de conteúdo por blocos
            "size": 0,
        }
        dir_struct = {
            "/": root_meta
        }

        # Criar arquivo binário e alocar tamanho (escrever zeros)
        with open(self.fs_path, "wb") as f:
            # alocar todo o tamanho com zeros (isso cria o arquivo do tamanho correto)
            f.truncate(total_bytes)

        # Montar estruturas em memória e salvar
        self.header = header
        self.fat = fat
        self.dir = dir_struct
        self._persist_metadata()
        self.mounted = True
        print(f"[create_fs] Criado FS '{self.fs_path}' {size_mb} MB, bloco {block_size} bytes, {total_blocks} blocos ({reserved_blocks} reservados).")

    def _persist_metadata(self):
        """
        Escreve header, fat e dir nos blocos reservados iniciais como um único blob pickled.
        A área reservada é definida por header['reserved_blocks'].
        """
        if self.header is None or self.fat is None or self.dir is None:
            raise RuntimeError("Estruturas não inicializadas.")
        block_size = self.header["block_size"]
        reserved = self.header["reserved_blocks"]
        # montar um objeto único para serializar
        meta = {
            "header": self.header,
            "fat": self.fat,
            "dir": self.dir
        }
        meta_bytes = pickle.dumps(meta)
        # verificar se cabe nos blocos reservados
        if len(meta_bytes) > reserved * block_size:
            raise RuntimeError("Metadados excedem área reservada. Aumente reserved_blocks ou tamanho do FS.")
        # abrir arquivo e escrever meta_bytes nos primeiros reserved blocos
        with open(self.fs_path, "r+b") as f:
            f.seek(0)
            # gravar meta_bytes e preencher o resto com zeros até reserved*block_size
            f.write(meta_bytes)
            remaining = reserved * block_size - len(meta_bytes)
            if remaining > 0:
                f.write(b'\x00' * remaining)
        # OK, persistido

    def _load_metadata(self):
        """
        Carrega header, fat e dir do arquivo .fs lendo os primeiros reserved blocks e desserializando.
        """
        if not os.path.exists(self.fs_path):
            raise FileNotFoundError("Arquivo .fs não encontrado.")
        # precisamos primeiro ler algum cabeçalho mínimo para descobrir reserved_blocks:
        # mas como header também está dentro da área, ler o primeiro block_size bytes e tentar pickle.
        # Simples: lemos os primeiros, por exemplo, 16 KB, e tentativa de unpickle. Se falhar, lemos mais.
        with open(self.fs_path, "rb") as f:
            # lemos uma quantidade razoável, depois unpickle
            # tentativa robusta: ler, por exemplo, first 1MB (mas sem extrapolar o arquivo)
            f.seek(0, os.SEEK_END)
            total_bytes = f.tell()
            to_read = min(total_bytes, 1024 * 1024)
            f.seek(0)
            blob = f.read(to_read)
            # tentar desempacotar: como gravamos tudo pickled, blob deve começar com pickle bytes
            try:
                meta = pickle.loads(blob)
            except Exception:
                # se falhar, lemos o total reservado (assumindo padrão small reserved)
                # alternativa: ler tudo e tentar
                f.seek(0)
                blob_all = f.read()
                meta = pickle.loads(blob_all)
        # meta deve conter header/fat/dir
        header = meta["header"]
        self.header = header
        self.fat = meta["fat"]
        self.dir = meta["dir"]
        self.mounted = True

    # ---------------------------
    # Helpers de bloco
    # ---------------------------

    def _block_offset(self, block_index: int) -> int:
        return block_index * self.header["block_size"]

    def _read_block(self, block_index: int) -> bytes:
        with open(self.fs_path, "rb") as f:
            f.seek(self._block_offset(block_index))
            return f.read(self.header["block_size"])

    def _write_block(self, block_index: int, data: bytes):
        """
        Escreve exatamente block_size bytes no bloco indicado.
        Se data < block_size, preenche com zeros. Se maior, corta (deve ser controlado).
        """
        bs = self.header["block_size"]
        if len(data) > bs:
            raise ValueError("Dados maiores que block_size.")
        with open(self.fs_path, "r+b") as f:
            f.seek(self._block_offset(block_index))
            f.write(data)
            if len(data) < bs:
                f.write(b'\x00' * (bs - len(data)))

    def _find_free_blocks(self, n: int):
        """
        Encontra n blocos livres na FAT e os retorna como lista.
        Retorna None se não houver espaço suficiente.
        """
        free_indices = [i for i, v in enumerate(self.fat) if v == 0]
        if len(free_indices) < n:
            return None
        return free_indices[:n]

    # ---------------------------
    # Operações de arquivo / diretório
    # ---------------------------

    def mount(self):
        """Carrega FS para memória (metadata)."""
        self._load_metadata()
        print(f"[mount] FS '{self.fs_path}' montado. Total {self.header['total_blocks']} blocos, bloco {self.header['block_size']} bytes.")

    def unmount(self):
        """Persistir e fechar (apenas persiste metadata)."""
        if not self.mounted:
            return
        self._persist_metadata()
        self.mounted = False
        print("[unmount] Metadata persistida e FS desmontado.")

    def pwd(self):
        return self.current_dir

    def _abs_path(self, path: str):
        """Resolve path relativo para absoluto dentro do FS."""
        if not path:
            return self.current_dir
        if path.startswith("/"):
            p = os.path.normpath(path).replace("\\", "/")  # Normalizar para usar sempre /
        else:
            p = os.path.normpath(os.path.join(self.current_dir, path)).replace("\\", "/")
        if p == ".":
            p = "/"
        # garantir barra inicial
        if not p.startswith("/"):
            p = "/" + p
        return p

    def mkdir(self, path: str):
        path = self._abs_path(path)
        if path in self.dir:
            raise FileExistsError("Diretório já existe.")
        parent = os.path.dirname(path).replace("\\", "/")
        if parent == "" or parent == ".":
            parent = "/"
        if parent not in self.dir or not self.dir[parent]["is_dir"]:
            raise FileNotFoundError("Diretório pai inexistente.")
        # criar entrada
        meta = {
            "is_dir": True,
            "name": os.path.basename(path),
            "parent": parent,
            "created": now_ts(),
            "modified": now_ts(),
            "protected": False,
            "blocks": [],
            "size": 0
        }
        self.dir[path] = meta
        self.header["last_modified"] = now_ts()
        self._persist_metadata()
        print(f"[mkdir] Diretório criado: {path}")

    def rmdir(self, path: str, recursive: bool = False):
        path = self._abs_path(path)
        if path not in self.dir or not self.dir[path]["is_dir"]:
            raise FileNotFoundError("Diretório não existe.")
        # verificar conteúdos
        children = [p for p in self.dir if os.path.dirname(p).replace("\\", "/") == path and p != path]
        if children and not recursive:
            raise OSError("Diretório não vazio. Use recursive=True para remover recursivamente.")
        # se recursive, remover todos filhos (arquivos e subdirs)
        to_remove = [p for p in self.dir if p == path or p.startswith(path + "/")]
        # Antes de remover, checar proteção
        for p in to_remove:
            if self.dir[p].get("protected", False):
                raise PermissionError(f"Entrada protegida: {p}")
        # liberar blocos de arquivos (se houver arquivos)
        for p in sorted(to_remove, key=lambda x: -len(x)):  # remover folhas primeiro
            meta = self.dir[p]
            if not meta["is_dir"]:
                # liberar blocos
                self._free_blocks_chain(meta["blocks"])
            del self.dir[p]
        self._persist_metadata()
        print(f"[rmdir] Removido: {path} (recursive={recursive})")

    def ls(self, path: str = None, show_hidden: bool = True):
        """Lista conteúdos do diretório em formato de tabela (pandas)."""
        if path is None:
            path = self.current_dir
        path = self._abs_path(path)
        if path not in self.dir or not self.dir[path]["is_dir"]:
            raise FileNotFoundError("Diretório inexistente.")
        # coletar filhos imediatos
        rows = []
        for p, meta in self.dir.items():
            if p == path:
                continue
            parent = meta.get("parent", "")
            if parent == path:
                rows.append({
                    "path": p,
                    "name": meta["name"],
                    "is_dir": meta["is_dir"],
                    "size": meta["size"],
                    "size_human": human_size(meta["size"]),
                    "protected": meta.get("protected", False),
                    "modified": datetime.fromtimestamp(meta.get("modified", 0)).isoformat()
                })
        if not rows:
            print(f"(vazio) diretório: {path}")
            return
        df = pd.DataFrame(rows).sort_values(["is_dir", "name"], ascending=[False, True])
        # Exibir tabela
        pd.set_option("display.max_colwidth", 200)
        print(df.reset_index(drop=True))

    def cd(self, path: str):
        path = self._abs_path(path)
        if path not in self.dir or not self.dir[path]["is_dir"]:
            raise FileNotFoundError("Diretório inexistente.")
        self.current_dir = path
        print(f"[cd] Diretório atual: {self.current_dir}")

    def stat(self, path: str):
        """Mostra informações detalhadas de um arquivo/diretório."""
        path = self._abs_path(path)
        if path not in self.dir:
            raise FileNotFoundError("Não encontrado.")
        meta = self.dir[path]
        info = {
            "path": path,
            "is_dir": meta["is_dir"],
            "size_bytes": meta["size"],
            "size_human": human_size(meta["size"]),
            "blocks": meta.get("blocks", []),
            "sha256": meta.get("sha256"),
            "protected": meta.get("protected", False),
            "created": datetime.fromtimestamp(meta.get("created", 0)).isoformat(),
            "modified": datetime.fromtimestamp(meta.get("modified", 0)).isoformat(),
        }
        for k, v in info.items():
            print(f"{k}: {v}")

    # ---------------------------
    # operações de bloco para arquivos
    # ---------------------------

    def _allocate_blocks_for_size(self, size_bytes: int):
        """
        Aloca a cadeia de blocos mínima para conter size_bytes.
        Retorna lista de índices de blocos encadeados na ordem física.
        """
        bs = self.header["block_size"]
        if size_bytes == 0:
            return []
        needed = math.ceil(size_bytes / bs)
        free = self._find_free_blocks(needed)
        if free is None:
            return None
        # marcar FAT: chain
        for i in range(needed):
            idx = free[i]
            if i == needed - 1:
                self.fat[idx] = -1  # terminador
            else:
                self.fat[idx] = free[i+1]
        return free[:needed]

    def _free_blocks_chain(self, blocks_list):
        """
        Libera blocos na FAT. blocks_list é a lista (sequência) de blocos que estavam alocados.
        """
        for b in blocks_list:
            if 0 <= b < len(self.fat):
                self.fat[b] = 0

    def _write_data_to_blocks(self, blocks_list, data_bytes):
        """
        Escreve data_bytes dividido por blocos em blocks_list (lista de índices).
        """
        bs = self.header["block_size"]
        total = len(data_bytes)
        for i, block_idx in enumerate(blocks_list):
            start = i * bs
            chunk = data_bytes[start:start + bs]
            self._write_block(block_idx, chunk)

    def _read_data_from_chain(self, blocks_list):
        bs = self.header["block_size"]
        parts = []
        for block_idx in blocks_list:
            chunk = self._read_block(block_idx)
            parts.append(chunk)
        data = b"".join(parts)
        # strip trailing zeros that might be padding (but we need to know exact size from metadata)
        return data

    # ---------------------------
    # copy_in / copy_out / remove / rename / protect
    # ---------------------------

    def copy_in(self, real_path: str, dest_path: str = None):
        """
        Copia arquivo do sistema real (real_path) para dentro do FS.
        dest_path: caminho relativo/absoluto dentro do FS (se None, usa mesmo nome no cwd)
        """
        if not os.path.exists(real_path) or not os.path.isfile(real_path):
            raise FileNotFoundError("Arquivo real não encontrado.")
        if not self.mounted:
            self.mount()
        with open(real_path, "rb") as f:
            content = f.read()
        fname = os.path.basename(real_path)
        if dest_path is None:
            dest_path = os.path.join(self.current_dir, fname).replace("\\", "/")
        dest_path = self._abs_path(dest_path)
        if dest_path in self.dir:
            # checar proteção
            if self.dir[dest_path].get("protected", False):
                raise PermissionError("Arquivo protegido – não pode sobrescrever.")
            # se existe e é arquivo, remover primeiro (liberar blocos)
            if not self.dir[dest_path]["is_dir"]:
                self._free_blocks_chain(self.dir[dest_path].get("blocks", []))
                del self.dir[dest_path]
        parent = os.path.dirname(dest_path).replace("\\", "/")
        if parent == "" or parent == ".":
            parent = "/"
        if parent not in self.dir or not self.dir[parent]["is_dir"]:
            raise FileNotFoundError("Diretório pai inexistente.")
        # alocar blocos
        blocks = self._allocate_blocks_for_size(len(content))
        if blocks is None:
            raise OSError("Espaço insuficiente.")
        # escrever conteúdo
        self._write_data_to_blocks(blocks, content)
        # salvar metadados
        meta = {
            "is_dir": False,
            "name": os.path.basename(dest_path),
            "parent": parent,
            "created": now_ts(),
            "modified": now_ts(),
            "protected": False,
            "blocks": blocks,
            "size": len(content),
            "sha256": sha256_bytes(content)
        }
        self.dir[dest_path] = meta
        self._persist_metadata()
        print(f"[copy_in] '{real_path}' -> '{dest_path}' ({human_size(len(content))})")

    def copy_out(self, fs_path: str, dest_real_dir: str, verify_integrity: bool = True):
        """
        Copia arquivo do FS para sistema real. dest_real_dir deve existir.
        """
        if not self.mounted:
            self.mount()
        fs_path = self._abs_path(fs_path)
        if fs_path not in self.dir:
            raise FileNotFoundError("Arquivo no FS não encontrado.")
        meta = self.dir[fs_path]
        if meta["is_dir"]:
            raise IsADirectoryError("Caminho no FS é um diretório.")
        if not os.path.isdir(dest_real_dir):
            raise NotADirectoryError("Destino real não é um diretório existente.")
        # ler dados
        blocks = meta.get("blocks", [])
        data = self._read_data_from_chain(blocks)
        # cortar para o tamanho exato
        data = data[:meta["size"]]
        out_path = os.path.join(dest_real_dir, meta["name"])
        with open(out_path, "wb") as f:
            f.write(data)
        if verify_integrity:
            h = sha256_bytes(data)
            ok = (h == meta.get("sha256"))
            print(f"[copy_out] Gravado em '{out_path}'. SHA256 ok? {ok}")
            if not ok:
                print(f"  esperado: {meta.get('sha256')}\n  obtido:   {h}")
        else:
            print(f"[copy_out] Gravado em '{out_path}'. (integridade não verificada)")
        return out_path

    def rm(self, path: str):
        """
        Remove arquivo do FS (não diretório). Verifica proteção.
        """
        if not self.mounted:
            self.mount()
        path = self._abs_path(path)
        if path not in self.dir:
            raise FileNotFoundError("Entrada não encontrada.")
        meta = self.dir[path]
        if meta.get("protected", False):
            raise PermissionError("Entrada protegida.")
        if meta["is_dir"]:
            raise IsADirectoryError("Caminho é diretório. Use rmdir.")
        # liberar blocos e remover
        self._free_blocks_chain(meta.get("blocks", []))
        del self.dir[path]
        self._persist_metadata()
        print(f"[rm] Removido arquivo: {path}")

    def rename(self, old_path: str, new_path: str):
        """
        Renomeia arquivo/diretório (movimenta se necessário).
        """
        if not self.mounted:
            self.mount()
        old_path = self._abs_path(old_path)
        new_path = self._abs_path(new_path)
        if old_path not in self.dir:
            raise FileNotFoundError("Origem não encontrada.")
        if new_path in self.dir:
            raise FileExistsError("Destino já existe.")
        meta = self.dir[old_path]
        if meta.get("protected", False):
            raise PermissionError("Origem protegida.")
        parent = os.path.dirname(new_path).replace("\\", "/")
        if parent == "" or parent == ".":
            parent = "/"
        if parent not in self.dir or not self.dir[parent]["is_dir"]:
            raise FileNotFoundError("Diretório pai do destino não existe.")
        # mover: atualizar key e parent/name
        new_meta = meta.copy()
        new_meta["name"] = os.path.basename(new_path)
        new_meta["parent"] = parent
        new_meta["modified"] = now_ts()
        # se é diretório, atualizar recursivamente paths dos filhos
        if meta["is_dir"]:
            # coletar todos filhos e renomear prefixo
            children = [p for p in self.dir if p.startswith(old_path + "/")]
            # criar novo entries
            for child in children:
                child_meta = self.dir[child]
                new_child_path = new_path + child[len(old_path):]
                self.dir[new_child_path] = child_meta.copy()
                # ajustar parent references for immediate children
                if child_meta.get("parent", "").startswith(old_path):
                    new_parent = new_path + child_meta["parent"][len(old_path):]
                    self.dir[new_child_path]["parent"] = new_parent
                del self.dir[child]
        # inserir novo e remover antigo
        self.dir[new_path] = new_meta
        del self.dir[old_path]
        self._persist_metadata()
        print(f"[rename] {old_path} -> {new_path}")

    def protect(self, path: str, protect: bool = True):
        """
        Protege/desprotege uma entrada contra remoção/alteração.
        """
        if not self.mounted:
            self.mount()
        path = self._abs_path(path)
        if path not in self.dir:
            raise FileNotFoundError("Entrada não encontrada.")
        self.dir[path]["protected"] = bool(protect)
        self._persist_metadata()
        print(f"[protect] {path} protegido={protect}")

    # ---------------------------
    # Espaço / utilitários
    # ---------------------------

    def space_info(self):
        """
        Retorna (total_bytes, used_bytes, free_bytes)
        """
        if not self.mounted:
            self.mount()
        total = self.header["fs_bytes"]
        # usado = blocos não-livres * block_size
        used_blocks = sum(1 for v in self.fat if v != 0)
        used = used_blocks * self.header["block_size"]
        free = total - used
        print(f"[space_info] {human_size(free)} livres de {human_size(total)} ({used_blocks}/{self.header['total_blocks']} blocos usados)")
        return total, used, free

    def df(self):
        """Mostra tabela de arquivos (todos) com metadados (pandas)."""
        rows = []
        for p, meta in self.dir.items():
            rows.append({
                "path": p,
                "name": meta["name"],
                "is_dir": meta["is_dir"],
                "size_bytes": meta["size"],
                "size_human": human_size(meta["size"]),
                "blocks": len(meta.get("blocks", [])),
                "protected": meta.get("protected", False)
            })
        df = pd.DataFrame(rows).sort_values(["is_dir", "path"], ascending=[False, True])
        pd.set_option("display.max_colwidth", 200)
        print(df.reset_index(drop=True))

    # ---------------------------
    # Extra: mostrar mapa FAT (simples)
    # ---------------------------

    def show_fat_map(self, limit=200):
        """Imprime os primeiros blocos da FAT (útil para debug)."""
        s = self.fat[:limit]
        print(s)

# ---------------------------
# Exemplo de uso / CLI mínima
# ---------------------------

if __name__ == "__main__":
    # exemplo prático - você pode adaptar conforme sua necessidade
    fsfile = "furgfs3.fs"
    fs = FURGfs3(fsfile)

    # 1) Criar arquivo FS (somente se não existir)
    if not os.path.exists(fsfile):
        print("Criando sistema de arquivos de 50 MB (padrão demo).")
        fs.create_fs(size_mb=50, block_size=4096)
    else:
        print("Arquivo .fs já existe, montando.")
        fs.mount()

    # Criar diretório /docs primeiro
    try:
        fs.mkdir("/docs")
        print("Diretório /docs criado com sucesso.")
    except FileExistsError:
        print("Diretório /docs já existe.")
    except Exception as e:
        print(f"Erro ao criar diretório /docs: {e}")

    # Criar arquivo de exemplo autores.txt localmente com os autores do enunciado
    autores_content = (
        "henrique bertochi grigol, 162647, henriquebg.bg@furg.br;"
        "vicenzo copetti, 164433, vicenzocopetti@furg.br;"
        "tiago pinheiro, 162649, tiagopinheiro@furg.br;"
    )
    
    # Criar o arquivo autores.txt no sistema real
    try:
        with open("autores.txt", "w", encoding="utf-8") as f:
            f.write(autores_content)
        print("Arquivo autores.txt criado no sistema real.")
    except Exception as e:
        print(f"Erro ao criar autores.txt: {e}")

    # Copiar para dentro do FS
    try:
        fs.copy_in("autores.txt", "/docs/autores.txt")
        print("Arquivo copiado para dentro do FS com sucesso.")
    except Exception as e:
        print(f"copy_in error: {e}")

    # Listar /docs
    print("\nListagem /docs:")
    try:
        fs.ls("/docs")
    except Exception as e:
        print(f"Erro ao listar /docs: {e}")

    # Mostrar espaço
    try:
        fs.space_info()
    except Exception as e:
        print(f"Erro ao mostrar espaço: {e}")

    # Copiar de volta para o diretório atual (verificando integridade)
    try:
        out = fs.copy_out("/docs/autores.txt", ".", verify_integrity=True)
        print(f"Arquivo copiado para: {out}")
    except Exception as e:
        print(f"copy_out error: {e}")

    # Mostrar tabela completa
    print("\nTabela completa de entradas no FS:")
    try:
        fs.df()
    except Exception as e:
        print(f"Erro ao mostrar tabela: {e}")

    # Protegendo o arquivo
    try:
        fs.protect("/docs/autores.txt", True)
        print("Arquivo protegido com sucesso.")
    except Exception as e:
        print(f"Erro ao proteger arquivo: {e}")

    # Tentar remover (vai falhar)
    try:
        fs.rm("/docs/autores.txt")
    except Exception as e:
        print(f"Tentativa de remover (esperado erro): {e}")

    # Desproteger e remover
    try:
        fs.protect("/docs/autores.txt", False)
        print("Arquivo desprotegido.")
        fs.rm("/docs/autores.txt")
        print("Arquivo removido com sucesso.")
    except Exception as e:
        print(f"Erro ao desproteger/remover: {e}")

    # Mostrar espaço final
    try:
        fs.space_info()
    except Exception as e:
        print(f"Erro ao mostrar espaço final: {e}")

    # Persistir e desmontar
    try:
        fs.unmount()
        print("FS desmontado com sucesso.")
    except Exception as e:
        print(f"Erro ao desmontar: {e}")