import os
import struct
import time
import hashlib
from typing import List, Dict, Tuple, Optional


class FURGfs3:
    # Constantes do sistema de arquivos
    BLOCK_SIZE = 1024           # Tamanho de cada bloco em bytes
    MAX_FILENAME = 32           # Tamanho máximo do nome do arquivo
    HEADER_SIZE = 128           # Tamanho do cabeçalho do sistema
    ENTRY_SIZE = 64             # Tamanho de cada entrada de diretório
    FAT_ENTRY_SIZE = 4          # Tamanho de cada entrada na FAT

    def __init__(self, filename: str = None):
        self.filename = filename
        self.file_handle = None     # Handle do arquivo do sistema
        self.header = {}            # Cabeçalho do sistema
        self.fat = []               # Tabela de alocação de arquivos (FAT)
        self.current_directory = 0  # Bloco do diretório atual
        self.directory_path = ["/"]  # Caminho atual
        self.script_dir = os.path.dirname(
            os.path.abspath(__file__))  # Pasta do script

    def _calculate_file_hash(self, content: bytes) -> str:
        """Calcula hash MD5 para verificação de integridade"""
        return hashlib.md5(content).hexdigest()

    def _read_file_from_fs(self, filename: str) -> bytes:
        """Lê o conteúdo completo de um arquivo do FURGfs3"""
        entries = self._read_directory()
        entry = next(
            (e for e in entries if e['name'] == filename and e['type'] == 0), None)
        if not entry:
            return None

        try:
            # Lê o arquivo bloco por bloco seguindo a cadeia da FAT
            content, current_block, bytes_left = b'', entry['start_block'], entry['size']
            while current_block != 1 and bytes_left > 0:
                block_start = self.header['data_start'] + \
                    (current_block - 1) * self.BLOCK_SIZE
                self.file_handle.seek(block_start)
                chunk_size = min(self.BLOCK_SIZE, bytes_left)
                content += self.file_handle.read(chunk_size)
                bytes_left -= chunk_size
                next_block = self.fat[current_block]
                if next_block in [1, 0]:
                    break  # Fim da cadeia
                current_block = next_block
            return content
        except Exception as e:
            print(f"Erro ao ler arquivo do FS: {e}")
            return None

    def create_filesystem(self, filename: str, size_mb: int) -> bool:
        """Cria um novo sistema de arquivos FURGfs3"""
        self.directory_path, self.current_directory = ["/"], 0
        if not filename.endswith('.fs'):
            filename += '.fs'
        if size_mb < 1 or size_mb > 10000:
            print("Erro: Tamanho deve estar entre 1MB e 10GB")
            return False

        # Calcula layout do sistema de arquivos
        full_path = os.path.join(self.script_dir, filename)
        total_bytes = size_mb * 1024 * 1024
        total_blocks = (total_bytes - self.HEADER_SIZE) // self.BLOCK_SIZE
        fat_start, fat_size = self.HEADER_SIZE, total_blocks * self.FAT_ENTRY_SIZE
        fat_blocks = (fat_size + self.BLOCK_SIZE - 1) // self.BLOCK_SIZE
        root_start = fat_start + fat_blocks * self.BLOCK_SIZE  # Diretório raiz
        data_start = root_start + self.BLOCK_SIZE              # Início dos dados

        try:
            with open(full_path, 'wb') as f:
                # Escreve cabeçalho com metadados do sistema
                header_data = struct.pack('<8I32s', self.HEADER_SIZE, self.BLOCK_SIZE, total_bytes,
                                          fat_start, root_start, data_start, total_blocks, 0,
                                          b'FURGfs3' + b'\x00' * 24)
                f.write(header_data.ljust(self.HEADER_SIZE, b'\x00'))

                # Inicializa FAT (todos blocos livres, exceto bloco 0 reservado)
                fat = [0] * total_blocks
                fat[0] = 1  # Bloco 0 reservado
                for entry in fat:
                    f.write(struct.pack('<I', entry & 0xFFFFFFFF))

                # Preenche resto do arquivo com zeros
                remaining = total_bytes - f.tell()
                while remaining > 0:
                    write_size = min(8192, remaining)
                    f.write(b'\x00' * write_size)
                    remaining -= write_size

            self.filename = full_path
            self._load_filesystem()

            # Cria arquivo autores.txt automaticamente
            authors = "henrique bertochi grigol, 162647, henriquebg.bg@furg.br;vicenzo copetti, 164433, vicenzocopetti@furg.br;tiago pinheiro, 162649, tiagopinheiro@furg.br;"
            self._create_file_in_fs("autores.txt", authors.encode())
            print(f"Sistema '{full_path}' criado ({size_mb}MB)")
            return True
        except Exception as e:
            print(f"Erro ao criar sistema: {e}")
            return False

    def _load_filesystem(self) -> bool:
        """Carrega um sistema de arquivos existente"""
        try:
            if not os.path.exists(self.filename):
                print(f"Arquivo '{self.filename}' não encontrado")
                return False

            file_size = os.path.getsize(self.filename)
            if file_size < self.HEADER_SIZE:
                print("Arquivo muito pequeno")
                return False

            self.file_handle = open(self.filename, 'r+b')
            header_data = self.file_handle.read(self.HEADER_SIZE)
            if len(header_data) < self.HEADER_SIZE:
                print("Não foi possível ler o cabeçalho")
                return False

            # Decodifica cabeçalho
            header_values = struct.unpack('<8I32s', header_data[:64])
            if not header_values[8].startswith(b'FURGfs3'):
                print("Assinatura inválida")
                return False

            # Armazena informações do cabeçalho
            self.header = {
                'header_size': header_values[0], 'block_size': header_values[1],
                'total_size': header_values[2], 'fat_start': header_values[3],
                'root_start': header_values[4], 'data_start': header_values[5],
                'total_blocks': header_values[6], 'free_blocks': header_values[7],
                'signature': header_values[8]
            }

            if self.header['total_size'] != file_size:
                print(f"Aviso: Tamanho no cabeçalho difere do real")

            # Carrega FAT na memória
            self.file_handle.seek(self.header['fat_start'])
            self.fat = [struct.unpack('<I', self.file_handle.read(4))[0]
                        for _ in range(self.header['total_blocks'])]

            self.current_directory, self.directory_path = 0, ["/"]
            return True
        except Exception as e:
            print(f"Erro ao carregar sistema: {e}")
            return False

    def _get_directory_block_position(self, block_num: int) -> int:
        """Retorna posição no arquivo para um bloco de diretório"""
        return self.header['root_start'] if block_num == 0 else self.header['data_start'] + (block_num - 1) * self.BLOCK_SIZE

    def _find_free_block(self) -> int:
        """Encontra primeiro bloco livre na FAT"""
        return next((i for i, entry in enumerate(self.fat) if entry == 0), -1)

    def _allocate_blocks(self, num_blocks: int) -> List[int]:
        """Aloca uma cadeia de blocos na FAT"""
        blocks = []
        for _ in range(num_blocks):
            block = self._find_free_block()
            if block == -1:
                # Rollback: libera blocos já alocados
                for b in blocks:
                    self.fat[b] = 0
                return []
            blocks.append(block)
            self.fat[block] = 1  # Marca como ocupado

        # Liga os blocos em cadeia
        for i in range(len(blocks) - 1):
            self.fat[blocks[i]] = blocks[i + 1]
        if blocks:
            self.fat[blocks[-1]] = 1  # Marca fim da cadeia
        return blocks

    def _calculate_directory_size(self, directory_block: int) -> int:
        """Calcula tamanho total recursivo de um diretório"""
        total_size = 0
        for entry in self._read_directory(directory_block):
            if entry['type'] == 0:
                total_size += entry['size']  # Arquivo
            elif entry['type'] == 1:
                # Subdiretório
                total_size += self._calculate_directory_size(
                    entry['start_block'])
        return total_size

    def _read_directory(self, directory_block: int = None, calculate_sizes: bool = False) -> List[Dict]:
        """Lê entradas do diretório especificado"""
        if directory_block is None:
            directory_block = self.current_directory
        dir_position = self._get_directory_block_position(directory_block)
        self.file_handle.seek(dir_position)
        entries = []

        # Lê todas as entradas possíveis no bloco de diretório
        for _ in range(self.BLOCK_SIZE // self.ENTRY_SIZE):
            data = self.file_handle.read(self.ENTRY_SIZE)
            if len(data) < self.ENTRY_SIZE or all(b == 0 for b in data):
                continue  # Entrada vazia

            try:
                # Decodifica estrutura da entrada de diretório
                values = struct.unpack('<32s4I2H12x', data)
                name_bytes, size, start_block, timestamp, protected_val, entry_type = values[
                    0], values[1], values[2], values[3], values[5], values[6]

                try:
                    name = name_bytes.rstrip(b'\x00').decode('utf-8')
                except:
                    continue

                # Valida nome do arquivo
                if not name or not all(32 <= ord(c) <= 126 or c.isspace() for c in name):
                    continue

                # Valida campos da entrada
                if (start_block >= len(self.fat) or entry_type not in [0, 1] or
                        protected_val not in [0, 1] or timestamp < 0 or timestamp > 2**31):
                    continue

                entry = {'name': name, 'size': size, 'start_block': start_block,
                         'timestamp': timestamp, 'protected': bool(protected_val), 'type': entry_type}

                # Calcula tamanho recursivo para diretórios se solicitado
                if calculate_sizes and entry['type'] == 1:
                    try:
                        entry['calculated_size'] = self._calculate_directory_size(
                            entry['start_block'])
                    except:
                        entry['calculated_size'] = 0

                entries.append(entry)
            except:
                continue
        return entries

    def _write_directory_entry(self, entry: Dict, position: int = -1, directory_block: int = None):
        """Escreve uma entrada no diretório"""
        if directory_block is None:
            directory_block = self.current_directory
        dir_position = self._get_directory_block_position(directory_block)

        # Encontra posição livre se não especificada
        if position == -1:
            self.file_handle.seek(dir_position)
            for pos in range(self.BLOCK_SIZE // self.ENTRY_SIZE):
                data = self.file_handle.read(self.ENTRY_SIZE)
                if len(data) < self.ENTRY_SIZE or data[0] == 0:
                    position = pos
                    break

        if position == -1:
            raise Exception("Diretório cheio")

        # Escreve entrada no diretório
        self.file_handle.seek(dir_position + position * self.ENTRY_SIZE)
        name_bytes = entry['name'].encode(
            'utf-8')[:self.MAX_FILENAME].ljust(self.MAX_FILENAME, b'\x00')
        data = struct.pack('<32s4I2H12x', name_bytes, entry['size'], entry['start_block'],
                           entry.get('timestamp', int(time.time())), 0,
                           int(entry.get('protected', False)), entry.get('type', 0))
        self.file_handle.write(data)

    def _item_operation(self, name: str, item_type: int, operation: str) -> bool:
        """Operação genérica para itens (arquivos/diretórios)"""
        entries = self._read_directory()
        for i, entry in enumerate(entries):
            if entry['name'] == name and entry['type'] == item_type:
                if entry.get('protected', False) and operation in ['remove', 'rename']:
                    print(
                        f"{'Arquivo' if item_type == 0 else 'Diretório'} protegido")
                    return False
                return i, entry
        print(f"{'Arquivo' if item_type == 0 else 'Diretório'} não encontrado")
        return False

    def create_directory(self, dirname: str) -> bool:
        """Cria um novo diretório"""
        if len(dirname) > self.MAX_FILENAME - 1:
            print("Nome muito longo")
            return False

        entries = self._read_directory()
        if any(e['name'] == dirname for e in entries):
            print("Diretório já existe")
            return False

        blocks = self._allocate_blocks(1)  # Diretório usa 1 bloco
        if not blocks:
            print("Espaço insuficiente")
            return False

        # Inicializa bloco do diretório com zeros
        dir_position = self.header['data_start'] + \
            (blocks[0] - 1) * self.BLOCK_SIZE
        self.file_handle.seek(dir_position)
        self.file_handle.write(b'\x00' * self.BLOCK_SIZE)

        # Cria entrada no diretório atual
        entry = {'name': dirname, 'size': 0, 'start_block': blocks[0],
                 'protected': False, 'type': 1, 'timestamp': int(time.time())}
        self._write_directory_entry(entry)
        self._update_fat()
        print(f"Diretório '{dirname}' criado")
        return True

    def change_directory(self, dirname: str) -> bool:
        """Muda para o diretório especificado"""
        if dirname == "..":  # Navegação para diretório pai
            if len(self.directory_path) > 1:
                self.directory_path.pop()
                if len(self.directory_path) == 1:
                    self.current_directory = 0  # Raiz
                else:
                    # Reconstroi caminho para encontrar bloco atual
                    current_block = 0
                    for path_part in self.directory_path[1:]:
                        entries = self._read_directory(current_block)
                        for entry in entries:
                            if entry['name'] == path_part and entry['type'] == 1:
                                current_block = entry['start_block']
                                break
                        else:
                            print(
                                f"Erro: Não foi possível encontrar '{path_part}'")
                            return False
                    self.current_directory = current_block
                print(f"Diretório atual: {self.get_current_path()}")
                return True
            else:
                print("Já está na raiz")
                return False

        # Navega para subdiretório
        entries = self._read_directory()
        for entry in entries:
            if entry['name'] == dirname and entry['type'] == 1:
                self.current_directory, self.directory_path = entry['start_block'], self.directory_path + [
                    dirname]
                print(f"Diretório atual: {self.get_current_path()}")
                return True
        print(f"Diretório '{dirname}' não encontrado")
        return False

    def remove_directory(self, dirname: str) -> bool:
        """Remove um diretório vazio"""
        result = self._item_operation(dirname, 1, 'remove')
        if not result:
            return False

        i, dir_entry = result
        if self._read_directory(dir_entry['start_block']):
            print("Diretório não está vazio")
            return False

        # Libera bloco do diretório
        self.fat[dir_entry['start_block']] = 0
        dir_position = self._get_directory_block_position(
            self.current_directory)
        self.file_handle.seek(dir_position + i * self.ENTRY_SIZE)
        self.file_handle.write(b'\x00' * self.ENTRY_SIZE)  # Limpa entrada
        self._update_fat()
        print(f"Diretório '{dirname}' removido")
        return True

    def _rename_item(self, old_name: str, new_name: str, item_type: int) -> bool:
        """Renomeia arquivo ou diretório"""
        if len(new_name) > self.MAX_FILENAME - 1:
            print("Nome muito longo")
            return False

        entries = self._read_directory()
        result = self._item_operation(old_name, item_type, 'rename')
        if not result:
            return False

        i, _ = result
        if any(e['name'] == new_name for e in entries):
            print("Nome já existe")
            return False

        # Atualiza nome na entrada
        entries[i]['name'] = new_name
        self._write_directory_entry(entries[i], i)
        item_name = "Diretório" if item_type == 1 else "Arquivo"
        print(f"{item_name} renomeado para '{new_name}'")
        return True

    def rename_directory(self, old_name: str, new_name: str) -> bool:
        return self._rename_item(old_name, new_name, 1)

    def rename_file(self, old_name: str, new_name: str) -> bool:
        return self._rename_item(old_name, new_name, 0)

    def _create_file_in_fs(self, filename: str, content: bytes) -> bool:
        """Cria um arquivo dentro do sistema de arquivos"""
        if len(filename) > self.MAX_FILENAME - 1:
            print("Nome muito longo")
            return False

        entries = self._read_directory()
        if any(e['name'] == filename for e in entries):
            print("Arquivo já existe")
            return False

        # Calcula quantos blocos são necessários
        num_blocks = max(
            1, (len(content) + self.BLOCK_SIZE - 1) // self.BLOCK_SIZE)
        blocks = self._allocate_blocks(num_blocks)
        if not blocks:
            print("Espaço insuficiente")
            return False

        # Escreve conteúdo nos blocos alocados
        offset = 0
        for block in blocks:
            block_start = self.header['data_start'] + \
                (block - 1) * self.BLOCK_SIZE
            self.file_handle.seek(block_start)
            chunk = content[offset:offset + self.BLOCK_SIZE]
            self.file_handle.write(chunk.ljust(
                self.BLOCK_SIZE, b'\x00'))  # Preenche com zeros
            offset += self.BLOCK_SIZE

        # Cria entrada no diretório
        entry = {'name': filename, 'size': len(content), 'start_block': blocks[0],
                 'protected': False, 'type': 0, 'timestamp': int(time.time())}
        self._write_directory_entry(entry)
        self._update_fat()
        return True

    def _update_fat(self):
        """Atualiza a FAT no arquivo (persiste no disco)"""
        self.file_handle.seek(self.header['fat_start'])
        for entry in self.fat:
            self.file_handle.write(struct.pack('<I', entry & 0xFFFFFFFF))
        self.file_handle.flush()

    def copy_to_fs(self, src_path: str, dst_name: str = None) -> bool:
        """Copia arquivo do sistema real para FURGfs3 com verificação de integridade"""
        src_path = src_path.strip('"\'')
        if not os.path.exists(src_path):
            print("Arquivo origem não encontrado")
            return False

        dst_name = dst_name.strip(
            '"\'') if dst_name else os.path.basename(src_path)

        try:
            with open(src_path, 'rb') as f:
                content = f.read()

            # Verificação de integridade com MD5
            original_hash = self._calculate_file_hash(content)
            print(f"Hash MD5 original: {original_hash}")

            success = self._create_file_in_fs(dst_name, content)

            if success:
                # Verifica se arquivo foi copiado sem corrupção
                verification_content = self._read_file_from_fs(dst_name)
                if verification_content:
                    verification_hash = self._calculate_file_hash(
                        verification_content)
                    print(f"Hash MD5 após cópia: {verification_hash}")

                    if original_hash == verification_hash:
                        print("✅ Integridade verificada")
                    else:
                        print("❌ ERRO: Arquivo corrompido!")
                        self.remove_file(dst_name)  # Remove arquivo corrompido
                        return False
                else:
                    print("⚠️  Não foi possível verificar integridade")

            return success
        except Exception as e:
            print(f"Erro ao copiar arquivo: {e}")
            return False

    def copy_from_fs(self, src_name: str, dst_path: str) -> bool:
        """Copia arquivo do FURGfs3 para sistema real com verificação de integridade"""
        entries = self._read_directory()
        entry = next(
            (e for e in entries if e['name'] == src_name and e['type'] == 0), None)
        if not entry:
            print("Arquivo não encontrado no FURGfs3")
            return False

        # Tratamento de caminhos de destino
        if os.path.exists(dst_path) and os.path.isdir(dst_path):
            dst_path = os.path.join(dst_path, src_name)
            print(f"Destino é diretório. Salvando como: {dst_path}")

        # Confirmações de segurança
        if dst_path.endswith('.fs'):
            print(f"⚠️  ATENÇÃO: '{dst_path}' parece ser um sistema FURGfs3!")
            if input("Tem certeza? Digite 'CONFIRMO': ") != 'CONFIRMO':
                print("Operação cancelada")
                return False
        elif os.path.exists(dst_path) and os.path.isfile(dst_path):
            if input(f"Arquivo '{dst_path}' já existe. Sobrescrever? (s/N): ").lower() != 's':
                print("Operação cancelada")
                return False

        try:
            content_from_fs = self._read_file_from_fs(src_name)
            if not content_from_fs:
                print("Erro: Não foi possível ler o arquivo do FURGfs3")
                return False

            # Verificação de integridade
            fs_hash = self._calculate_file_hash(content_from_fs)
            print(f"Hash MD5 no FS: {fs_hash}")

            # Cria diretório pai se necessário
            parent_dir = os.path.dirname(dst_path)
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir, exist_ok=True)

            # Escreve no sistema real
            with open(dst_path, 'wb') as f:
                f.write(content_from_fs)

            # Verifica integridade após cópia
            with open(dst_path, 'rb') as f:
                written_content = f.read()
            written_hash = self._calculate_file_hash(written_content)
            print(f"Hash MD5 após cópia: {written_hash}")

            if fs_hash == written_hash:
                print("✅ Integridade verificada")
                print(f"Arquivo copiado para {dst_path}")
                return True
            else:
                print("❌ ERRO: Arquivo corrompido!")
                try:
                    os.remove(dst_path)  # Remove arquivo corrompido
                except:
                    pass
                return False

        except Exception as e:
            print(f"Erro ao copiar arquivo: {e}")
            return False

    def remove_file(self, filename: str) -> bool:
        """Remove um arquivo liberando seus blocos na FAT"""
        entries = self._read_directory()
        entry = next(
            (e for e in entries if e['name'] == filename and e['type'] == 0), None)
        if not entry:
            print("Arquivo não encontrado")
            return False
        if entry.get('protected', False):
            print("Arquivo protegido")
            return False

        # Libera cadeia de blocos na FAT
        current_block = entry['start_block']
        while current_block not in [1, 0]:
            next_block = self.fat[current_block]
            self.fat[current_block] = 0  # Marca como livre
            current_block = next_block if next_block != 1 else 0

        # Remove entrada do diretório
        entries_pos = self._read_directory()
        for i, e in enumerate(entries_pos):
            if e['name'] == filename and e['type'] == 0:
                dir_position = self._get_directory_block_position(
                    self.current_directory)
                self.file_handle.seek(dir_position + i * self.ENTRY_SIZE)
                self.file_handle.write(
                    b'\x00' * self.ENTRY_SIZE)  # Zera entrada
                break

        self._update_fat()
        print(f"Arquivo {filename} removido")
        return True

    def list_files(self) -> List[Dict]:
        """Lista arquivos no diretório atual com tamanhos calculados"""
        return self._read_directory(calculate_sizes=True)

    def _format_size(self, bytes_size: int) -> str:
        """Formata tamanho em bytes para leitura humana"""
        if bytes_size >= 1024 * 1024:
            return f"{bytes_size} bytes ({bytes_size / (1024 * 1024):.2f} MB)"
        elif bytes_size >= 1024:
            return f"{bytes_size} bytes ({bytes_size / 1024:.2f} KB)"
        return f"{bytes_size} bytes"

    def get_space_info(self) -> Tuple[int, int]:
        """Retorna espaço livre e total em bytes"""
        try:
            if not hasattr(self, 'fat') or not self.fat:
                return (0, 0)
            free_blocks = sum(1 for x in self.fat if x == 0)
            # Calcula blocos usados por metadados
            fat_blocks = (len(self.fat) * self.FAT_ENTRY_SIZE +
                          self.BLOCK_SIZE - 1) // self.BLOCK_SIZE
            header_blocks = (self.HEADER_SIZE +
                             self.BLOCK_SIZE - 1) // self.BLOCK_SIZE
            metadata_blocks = fat_blocks + header_blocks + 1  # +1 para diretório raiz
            total_data_blocks = len(self.fat) - metadata_blocks
            return free_blocks * self.BLOCK_SIZE, total_data_blocks * self.BLOCK_SIZE
        except Exception as e:
            print(f"Erro ao calcular espaço: {e}")
            return (0, 0)

    def get_space_info_formatted(self) -> Tuple[str, str, str]:
        """Retorna espaço formatado para exibição"""
        try:
            free_bytes, total_bytes = self.get_space_info()
            used_bytes = total_bytes - free_bytes
            return (self._format_size(free_bytes), self._format_size(used_bytes), self._format_size(total_bytes))
        except Exception as e:
            print(f"Erro ao formatar espaço: {e}")
            return ("0 bytes", "0 bytes", "0 bytes")

    def toggle_protection(self, filename: str) -> bool:
        """Alterna proteção de um arquivo ou diretório"""
        entries = self._read_directory()
        for i, entry in enumerate(entries):
            if entry['name'] == filename:
                entry['protected'] = not entry.get('protected', False)
                self._write_directory_entry(entry, i)
                status = "protegido" if entry['protected'] else "desprotegido"
                item_type = "Diretório" if entry['type'] == 1 else "Arquivo"
                print(f"{item_type} {filename} {status}")
                return True
        print("Item não encontrado")
        return False

    def verify_file_integrity(self, filename: str) -> bool:
        """Verifica manualmente a integridade de um arquivo"""
        entries = self._read_directory()
        entry = next(
            (e for e in entries if e['name'] == filename and e['type'] == 0), None)
        if not entry:
            print("Arquivo não encontrado")
            return False

        content = self._read_file_from_fs(filename)
        if content:
            file_hash = self._calculate_file_hash(content)
            print(f"Hash MD5 do '{filename}': {file_hash}")
            print(f"Tamanho: {self._format_size(len(content))}")
            return True
        else:
            print("Não foi possível ler o arquivo")
            return False

    def get_current_path(self) -> str:
        """Retorna o caminho atual como string"""
        if not hasattr(self, 'directory_path') or not self.directory_path:
            return "/"
        return "/" if len(self.directory_path) == 1 else "/".join(self.directory_path)

    def close(self):
        """Fecha o sistema de arquivos"""
        if self.file_handle:
            self.file_handle.close()


def main():
    """Menu principal interativo"""
    fs = FURGfs3()

    while True:
        # Exibe caminho atual no prompt
        current_path = fs.get_current_path() if hasattr(
            fs, 'filename') and fs.filename and hasattr(fs, 'get_current_path') else "/"
        print(f"\n=== FURGfs3 [{current_path}] ===")
        print("1. Criar sistema\n2. Abrir sistema\n3. Copiar para FS\n4. Copiar do FS\n5. Renomear arquivo")
        print("6. Remover arquivo\n7. Listar\n8. Espaço\n9. Proteger/Desproteger\n10. Criar dir\n11. Entrar dir")
        print("12. Renomear dir\n13. Remover dir\n14. Verificar integridade\n0. Sair")

        try:
            opcao = input("Opção: ").strip()

            if opcao == '1':
                # Cria novo sistema de arquivos
                nome, tamanho = input("Nome do sistema (sem .fs): "), int(
                    input("Tamanho MB (1-10000): "))
                if fs.create_filesystem(nome, tamanho) and fs._load_filesystem():
                    print("Sistema criado e carregado com sucesso!")

            elif opcao == '2':
                # Carrega sistema existente
                nome = input("Nome (.fs): ")
                if not nome.endswith('.fs'):
                    nome += '.fs'
                full_path = os.path.join(fs.script_dir, nome)
                if os.path.exists(full_path):
                    fs.filename = full_path
                elif os.path.exists(nome):
                    fs.filename = nome
                else:
                    print("Arquivo não encontrado")
                    continue

                if fs._load_filesystem():
                    print("Sistema carregado")
                    # Exibe informações do sistema
                    free_f, used_f, total_f = fs.get_space_info_formatted()
                    print(
                        f"Total: {total_f}, Usado: {used_f}, Livre: {free_f}")
                    arquivos = fs.list_files()
                    if arquivos:
                        print(f"Itens ({len(arquivos)}):")
                        for arq in arquivos:
                            timestamp = time.strftime(
                                '%Y-%m-%d %H:%M:%S', time.localtime(arq.get('timestamp', 0)))
                            protected = " [P]" if arq.get(
                                'protected', False) else ""
                            item_type = "[DIR]" if arq['type'] == 1 else "[ARQ]"
                            if arq['type'] == 1:
                                size_info = f"({fs._format_size(arq.get('calculated_size', 0))})" if arq.get(
                                    'calculated_size', 0) > 0 else "(vazio)"
                            else:
                                size_info = f"({fs._format_size(arq['size'])})"
                            print(
                                f"  {item_type} {arq['name']} {size_info} {timestamp}{protected}")

            elif opcao in ['3', '4', '5', '6', '7', '8', '9', '10', '11', '12', '13', '14']:
                if not fs.filename:
                    print("Nenhum sistema carregado")
                    continue

                if opcao == '3':
                    origem, destino = input("Arquivo origem: "), input(
                        "Nome no FS (Enter=mesmo): ").strip()
                    fs.copy_to_fs(origem, destino if destino else None)
                elif opcao == '4':
                    origem, destino = input(
                        "Arquivo no FS: "), input("Destino: ")
                    fs.copy_from_fs(origem, destino)
                elif opcao == '5':
                    antigo, novo = input("Nome atual: "), input("Novo nome: ")
                    fs.rename_file(antigo, novo)
                elif opcao == '6':
                    nome = input("Arquivo: ")
                    if input(f"Remover '{nome}'? (s/N): ").lower() == 's':
                        fs.remove_file(nome)
                elif opcao == '7':
                    # Listagem formatada
                    arquivos = fs.list_files()
                    if arquivos:
                        print(
                            f"{'Tipo':<6} {'Nome':<20} {'Tamanho':<25} {'P':<2} {'Data':<20}")
                        print("-" * 73)
                        for arq in arquivos:
                            timestamp = time.strftime(
                                '%Y-%m-%d %H:%M:%S', time.localtime(arq.get('timestamp', 0)))
                            protected = "S" if arq.get(
                                'protected', False) else "N"
                            item_type = "[DIR]" if arq['type'] == 1 else "[ARQ]"
                            if arq['type'] == 1:
                                size_info = fs._format_size(arq.get('calculated_size', 0)) if arq.get(
                                    'calculated_size', 0) > 0 else "vazio"
                            else:
                                size_info = fs._format_size(arq['size'])
                            print(
                                f"{item_type:<6} {arq['name']:<20} {size_info:<25} {protected:<2} {timestamp}")
                    else:
                        print("Nenhum item encontrado")
                elif opcao == '8':
                    free_f, used_f, total_f = fs.get_space_info_formatted()
                    print(
                        f"Total: {total_f}, Usado: {used_f}, Livre: {free_f}")
                elif opcao == '9':
                    fs.toggle_protection(input("Nome: "))
                elif opcao == '10':
                    fs.create_directory(input("Nome do diretório: "))
                elif opcao == '11':
                    fs.change_directory(input("Diretório (.. para voltar): "))
                elif opcao == '12':
                    antigo, novo = input("Nome atual: "), input("Novo nome: ")
                    fs.rename_directory(antigo, novo)
                elif opcao == '13':
                    nome = input("Diretório a remover: ")
                    if input(f"Remover '{nome}'? (s/N): ").lower() == 's':
                        fs.remove_directory(nome)
                elif opcao == '14':
                    fs.verify_file_integrity(
                        input("Arquivo para verificar integridade: "))

            elif opcao == '0':
                fs.close()
                print("Sistema fechado!")
                break
            else:
                print("\nOpção inválida!")

        except KeyboardInterrupt:
            fs.close()
            print("\nSistema fechado.")
            break
        except Exception as e:
            print(f"Erro: {e}")


if __name__ == "__main__":
    main()