import os
import struct
import time
from typing import List, Dict, Tuple, Optional

class FURGfs3:
    BLOCK_SIZE = 1024
    MAX_FILENAME = 32
    HEADER_SIZE = 128
    ENTRY_SIZE = 64
    FAT_ENTRY_SIZE = 4

    def __init__(self, filename: str = None):
        self.filename = filename
        self.file_handle = None
        self.header = {}
        self.fat = []
        self.current_directory = 0
        self.directory_path = ["/"]

    def create_filesystem(self, filename: str, size_mb: int) -> bool:
        """Cria um novo sistema de arquivos FURGfs3"""
        if not filename.endswith('.fs'):
            filename += '.fs'
        if size_mb < 1 or size_mb > 10000:
            print("Erro: Tamanho deve estar entre 1MB e 10GB")
            return False

        total_bytes = size_mb * 1024 * 1024
        total_blocks = (total_bytes - self.HEADER_SIZE) // self.BLOCK_SIZE
        fat_start = self.HEADER_SIZE
        fat_size = total_blocks * self.FAT_ENTRY_SIZE
        fat_blocks = (fat_size + self.BLOCK_SIZE - 1) // self.BLOCK_SIZE
        root_start = fat_start + fat_blocks * self.BLOCK_SIZE
        data_start = root_start + self.BLOCK_SIZE

        try:
            with open(filename, 'wb') as f:
                header_data = struct.pack('<8I32s', self.HEADER_SIZE, self.BLOCK_SIZE,
                                          total_bytes, fat_start, root_start, data_start,
                                          total_blocks, 0, b'FURGfs3' + b'\x00' * 24)
                f.write(header_data.ljust(self.HEADER_SIZE, b'\x00'))

                fat = [0] * total_blocks
                fat[0] = 1
                for entry in fat:
                    f.write(struct.pack('<I', entry & 0xFFFFFFFF))

                remaining = total_bytes - f.tell()
                chunk_size = 8192
                while remaining > 0:
                    write_size = min(chunk_size, remaining)
                    f.write(b'\x00' * write_size)
                    remaining -= write_size

            self.filename = filename
            self._load_filesystem()
            authors_content = "henrique bertochi grigol, 162647, henriquebg.bg@furg.br;vicenzo copetti, 164433, vicenzocopetti@furg.br;tiago pinheiro, 162649, tiagopinheiro@furg.br;"
            self._create_file_in_fs("autores.txt", authors_content.encode())
            print(f"Sistema de arquivos '{filename}' criado com sucesso ({size_mb}MB)")
            return True
        except Exception as e:
            print(f"Erro ao criar sistema de arquivos: {e}")
            return False

    def _load_filesystem(self) -> bool:
        """Carrega um sistema de arquivos existente"""
        try:
            if not os.path.exists(self.filename):
                print(f"Arquivo '{self.filename}' não encontrado")
                return False
            
            file_size = os.path.getsize(self.filename)
            if file_size < self.HEADER_SIZE:
                print(f"Erro: Arquivo muito pequeno ({file_size} bytes). Não é um sistema FURGfs3 válido.")
                return False

            self.file_handle = open(self.filename, 'r+b')
            self.file_handle.seek(0)
            header_data = self.file_handle.read(self.HEADER_SIZE)
            
            if len(header_data) < self.HEADER_SIZE:
                print("Erro: Não foi possível ler o cabeçalho completo")
                return False
                
            header_values = struct.unpack('<8I32s', header_data[:64])
            signature = header_values[8]
            if not signature.startswith(b'FURGfs3'):
                print("Erro: Assinatura inválida. Este não é um arquivo FURGfs3 válido.")
                return False

            self.header = {
                'header_size': header_values[0], 'block_size': header_values[1],
                'total_size': header_values[2], 'fat_start': header_values[3],
                'root_start': header_values[4], 'data_start': header_values[5],
                'total_blocks': header_values[6], 'free_blocks': header_values[7],
                'signature': header_values[8]
            }

            if self.header['total_size'] != file_size:
                print(f"Aviso: Tamanho no cabeçalho ({self.header['total_size']}) difere do arquivo real ({file_size})")

            self.file_handle.seek(self.header['fat_start'])
            self.fat = []
            for i in range(self.header['total_blocks']):
                fat_data = self.file_handle.read(4)
                if len(fat_data) < 4:
                    print(f"Erro: FAT truncada no bloco {i}")
                    return False
                entry = struct.unpack('<I', fat_data)[0]
                self.fat.append(entry)

            self.current_directory = 0
            self.directory_path = ["/"]
            return True
        except Exception as e:
            print(f"Erro ao carregar sistema de arquivos: {e}")
            return False

    def _get_directory_block_position(self, block_num: int) -> int:
        """Retorna a posição no arquivo para um bloco de diretório"""
        if block_num == 0:
            return self.header['root_start']
        return self.header['data_start'] + (block_num - 1) * self.BLOCK_SIZE

    def _find_free_block(self) -> int:
        """Encontra um bloco livre"""
        for i, entry in enumerate(self.fat):
            if entry == 0:
                return i
        return -1

    def _allocate_blocks(self, num_blocks: int) -> List[int]:
        """Aloca uma cadeia de blocos"""
        blocks = []
        for _ in range(num_blocks):
            block = self._find_free_block()
            if block == -1:
                for b in blocks:
                    self.fat[b] = 0
                return []
            blocks.append(block)
            self.fat[block] = 1

        for i in range(len(blocks) - 1):
            self.fat[blocks[i]] = blocks[i + 1]
        if blocks:
            self.fat[blocks[-1]] = 1
        return blocks

    def _calculate_directory_size(self, directory_block: int) -> int:
        """Calcula o tamanho total de um diretório"""
        total_size = 0
        entries = self._read_directory(directory_block)
        for entry in entries:
            if entry['type'] == 0:
                total_size += entry['size']
            elif entry['type'] == 1:
                total_size += self._calculate_directory_size(entry['start_block'])
        return total_size

    def _read_directory(self, directory_block: int = None, calculate_sizes: bool = False) -> List[Dict]:
        """Lê entradas do diretório especificado"""
        if directory_block is None:
            directory_block = self.current_directory
        
        dir_position = self._get_directory_block_position(directory_block)
        self.file_handle.seek(dir_position)
        entries = []

        for entry_pos in range(self.BLOCK_SIZE // self.ENTRY_SIZE):
            data = self.file_handle.read(self.ENTRY_SIZE)
            if len(data) < self.ENTRY_SIZE:
                continue
                
            # Verificar se a entrada está vazia (todos os bytes são 0)
            if all(b == 0 for b in data):
                continue

            try:
                values = struct.unpack('<32s4I2H12x', data)
                name_bytes = values[0]
                
                try:
                    name = name_bytes.rstrip(b'\x00').decode('utf-8')
                except UnicodeDecodeError:
                    continue
                
                if not name or not all(32 <= ord(c) <= 126 or c.isspace() for c in name):
                    continue
                
                size, start_block, timestamp, protected_val, entry_type = values[1], values[2], values[3], values[5], values[6]
                
                if (start_block >= len(self.fat) or entry_type not in [0, 1] or 
                    protected_val not in [0, 1] or timestamp < 0 or timestamp > 2**31):
                    continue

                entry = {
                    'name': name, 'size': size, 'start_block': start_block,
                    'timestamp': timestamp, 'reserved': values[4],
                    'protected': bool(protected_val), 'type': entry_type
                }
                
                if calculate_sizes and entry['type'] == 1:
                    try:
                        entry['calculated_size'] = self._calculate_directory_size(entry['start_block'])
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
        
        if position == -1:
            self.file_handle.seek(dir_position)
            for pos in range(self.BLOCK_SIZE // self.ENTRY_SIZE):
                data = self.file_handle.read(self.ENTRY_SIZE)
                if len(data) < self.ENTRY_SIZE or data[0] == 0:
                    position = pos
                    break

        if position == -1:
            raise Exception("Diretório cheio")

        self.file_handle.seek(dir_position + position * self.ENTRY_SIZE)
        name_bytes = entry['name'].encode('utf-8')[:self.MAX_FILENAME]
        name_bytes = name_bytes.ljust(self.MAX_FILENAME, b'\x00')

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
                    print(f"{'Arquivo' if item_type == 0 else 'Diretório'} protegido")
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

        blocks = self._allocate_blocks(1)
        if not blocks:
            print("Espaço insuficiente")
            return False

        dir_position = self.header['data_start'] + (blocks[0] - 1) * self.BLOCK_SIZE
        self.file_handle.seek(dir_position)
        self.file_handle.write(b'\x00' * self.BLOCK_SIZE)

        entry = {'name': dirname, 'size': 0, 'start_block': blocks[0],
                 'protected': False, 'type': 1, 'timestamp': int(time.time())}
        self._write_directory_entry(entry)
        self._update_fat()
        print(f"Diretório '{dirname}' criado")
        return True

    def change_directory(self, dirname: str) -> bool:
        """Muda para o diretório especificado"""
        if dirname == "..":
            if len(self.directory_path) > 1:
                self.directory_path.pop()
                if len(self.directory_path) == 1:
                    self.current_directory = 0
                else:
                    current_block = 0
                    for path_part in self.directory_path[1:]:
                        entries = self._read_directory(current_block)
                        found = False
                        for entry in entries:
                            if entry['name'] == path_part and entry['type'] == 1:
                                current_block = entry['start_block']
                                found = True
                                break
                        if not found:
                            print(f"Erro: Não foi possível encontrar '{path_part}'")
                            return False
                    self.current_directory = current_block
                path_display = self.get_current_path()
                print(f"Diretório atual: {path_display}")
                return True
            else:
                print("Já está na raiz")
                return False

        entries = self._read_directory()
        for entry in entries:
            if entry['name'] == dirname and entry['type'] == 1:
                self.current_directory = entry['start_block']
                self.directory_path.append(dirname)
                path_display = self.get_current_path()
                print(f"Diretório atual: {path_display}")
                return True
        print(f"Diretório '{dirname}' não encontrado")
        return False

    def remove_directory(self, dirname: str) -> bool:
        """Remove um diretório vazio"""
        result = self._item_operation(dirname, 1, 'remove')
        if not result:
            return False
        
        i, dir_entry = result
        dir_entries = self._read_directory(dir_entry['start_block'])
        if dir_entries:
            print("Diretório não está vazio")
            return False

        self.fat[dir_entry['start_block']] = 0
        dir_position_in_file = self._get_directory_block_position(self.current_directory)
        self.file_handle.seek(dir_position_in_file + i * self.ENTRY_SIZE)
        self.file_handle.write(b'\x00' * self.ENTRY_SIZE)
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

        entries[i]['name'] = new_name
        self._write_directory_entry(entries[i], i)
        item_name = "Diretório" if item_type == 1 else "Arquivo"
        print(f"{item_name} renomeado para '{new_name}'")
        return True

    def rename_directory(self, old_name: str, new_name: str) -> bool:
        """Renomeia um diretório"""
        return self._rename_item(old_name, new_name, 1)

    def rename_file(self, old_name: str, new_name: str) -> bool:
        """Renomeia um arquivo"""
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

        num_blocks = max(1, (len(content) + self.BLOCK_SIZE - 1) // self.BLOCK_SIZE)
        blocks = self._allocate_blocks(num_blocks)
        if not blocks:
            print("Espaço insuficiente")
            return False

        offset = 0
        for block in blocks:
            block_start = self.header['data_start'] + (block - 1) * self.BLOCK_SIZE
            self.file_handle.seek(block_start)
            chunk = content[offset:offset + self.BLOCK_SIZE]
            self.file_handle.write(chunk.ljust(self.BLOCK_SIZE, b'\x00'))
            offset += self.BLOCK_SIZE

        entry = {'name': filename, 'size': len(content), 'start_block': blocks[0],
                 'protected': False, 'type': 0, 'timestamp': int(time.time())}
        self._write_directory_entry(entry)
        self._update_fat()
        return True

    def _update_fat(self):
        """Atualiza a FAT no arquivo"""
        self.file_handle.seek(self.header['fat_start'])
        for entry in self.fat:
            self.file_handle.write(struct.pack('<I', entry & 0xFFFFFFFF))
        self.file_handle.flush()

    def copy_to_fs(self, src_path: str, dst_name: str = None) -> bool:
        """Copia arquivo do sistema real para FURGfs3"""
        if not os.path.exists(src_path):
            print("Arquivo origem não encontrado")
            return False

        if dst_name is None:
            dst_name = os.path.basename(src_path)

        try:
            with open(src_path, 'rb') as f:
                content = f.read()
            return self._create_file_in_fs(dst_name, content)
        except Exception as e:
            print(f"Erro ao copiar arquivo: {e}")
            return False

    def copy_from_fs(self, src_name: str, dst_path: str) -> bool:
        """Copia arquivo do FURGfs3 para sistema real"""
        entries = self._read_directory()
        entry = next((e for e in entries if e['name'] == src_name and e['type'] == 0), None)

        if not entry:
            print("Arquivo não encontrado no FURGfs3")
            return False

        if os.path.exists(dst_path) and os.path.isdir(dst_path):
            dst_path = os.path.join(dst_path, src_name)
            print(f"Destino é um diretório. Salvando como: {dst_path}")

        if dst_path.endswith('.fs'):
            print(f"⚠️  ATENÇÃO: '{dst_path}' parece ser um sistema FURGfs3!")
            response = input("Tem certeza? Digite 'CONFIRMO': ")
            if response != 'CONFIRMO':
                print("Operação cancelada")
                return False
        elif os.path.exists(dst_path) and os.path.isfile(dst_path):
            response = input(f"Arquivo '{dst_path}' já existe. Sobrescrever? (s/N): ")
            if response.lower() != 's':
                print("Operação cancelada")
                return False

        try:
            content = b''
            current_block = entry['start_block']
            bytes_left = entry['size']

            while current_block != 1 and bytes_left > 0:
                block_start = self.header['data_start'] + (current_block - 1) * self.BLOCK_SIZE
                self.file_handle.seek(block_start)
                chunk_size = min(self.BLOCK_SIZE, bytes_left)
                chunk = self.file_handle.read(chunk_size)
                content += chunk
                bytes_left -= chunk_size
                next_block = self.fat[current_block]
                if next_block in [1, 0]:
                    break
                current_block = next_block

            parent_dir = os.path.dirname(dst_path)
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir, exist_ok=True)

            with open(dst_path, 'wb') as f:
                f.write(content)
            print(f"Arquivo copiado para {dst_path}")
            return True
        except Exception as e:
            print(f"Erro ao copiar arquivo: {e}")
            return False

    def remove_file(self, filename: str) -> bool:
        """Remove um arquivo"""
        entries = self._read_directory()
        entry = next((e for e in entries if e['name'] == filename and e['type'] == 0), None)

        if not entry:
            print("Arquivo não encontrado")
            return False
        if entry.get('protected', False):
            print("Arquivo protegido")
            return False

        current_block = entry['start_block']
        while current_block not in [1, 0]:
            next_block = self.fat[current_block]
            self.fat[current_block] = 0
            current_block = next_block if next_block != 1 else 0

        entries_pos = self._read_directory()
        for i, e in enumerate(entries_pos):
            if e['name'] == filename and e['type'] == 0:
                dir_position = self._get_directory_block_position(self.current_directory)
                self.file_handle.seek(dir_position + i * self.ENTRY_SIZE)
                self.file_handle.write(b'\x00' * self.ENTRY_SIZE)
                break

        self._update_fat()
        print(f"Arquivo {filename} removido")
        return True

    def list_files(self) -> List[Dict]:
        """Lista arquivos no diretório atual"""
        return self._read_directory(calculate_sizes=True)

    def _format_size(self, bytes_size: int) -> str:
        """Formata tamanho em bytes"""
        if bytes_size >= 1024 * 1024:
            return f"{bytes_size} bytes ({bytes_size / (1024 * 1024):.2f} MB)"
        elif bytes_size >= 1024:
            return f"{bytes_size} bytes ({bytes_size / 1024:.2f} KB)"
        return f"{bytes_size} bytes"

    def get_space_info(self) -> Tuple[int, int]:
        """Retorna espaço livre e total"""
        free_blocks = sum(1 for x in self.fat if x == 0)
        fat_blocks = (len(self.fat) * self.FAT_ENTRY_SIZE + self.BLOCK_SIZE - 1) // self.BLOCK_SIZE
        header_blocks = (self.HEADER_SIZE + self.BLOCK_SIZE - 1) // self.BLOCK_SIZE
        metadata_blocks = fat_blocks + header_blocks + 1
        total_data_blocks = len(self.fat) - metadata_blocks
        return free_blocks * self.BLOCK_SIZE, total_data_blocks * self.BLOCK_SIZE

    def get_space_info_formatted(self) -> Tuple[str, str, str]:
        """Retorna espaço formatado"""
        free_bytes, total_bytes = self.get_space_info()
        used_bytes = total_bytes - free_bytes
        return (self._format_size(free_bytes), self._format_size(used_bytes), self._format_size(total_bytes))

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

    def get_current_path(self) -> str:
        """Retorna o caminho atual"""
        return "/" if len(self.directory_path) == 1 else "/".join(self.directory_path)

    def close(self):
        """Fecha o sistema de arquivos"""
        if self.file_handle:
            self.file_handle.close()


def main():
    """Menu principal"""
    fs = FURGfs3()

    while True:
        current_path = fs.get_current_path() if fs.filename else "/"
        print(f"\n=== FURGfs3 [{current_path}] ===")
        print("1. Criar sistema  2. Abrir sistema  3. Copiar para FS  4. Copiar do FS")
        print("5. Renomear arquivo  6. Remover arquivo  7. Listar  8. Espaço")
        print("9. Proteger/Desproteger  10. Criar dir  11. Entrar dir  12. Remover dir")
        print("13. Renomear dir  0. Sair")

        try:
            opcao = input("Opção: ").strip()

            if opcao == '1':
                nome = input("Nome do sistema (sem .fs): ")
                tamanho = int(input("Tamanho MB (1-10000): "))
                if fs.create_filesystem(nome, tamanho):
                    fs.filename = nome + '.fs' if not nome.endswith('.fs') else nome
                    fs._load_filesystem()

            elif opcao == '2':
                nome = input("Nome (.fs): ")
                if not nome.endswith('.fs'):
                    nome += '.fs'
                if os.path.exists(nome):
                    fs.filename = nome
                    if fs._load_filesystem():
                        print("Sistema carregado")
                        free_f, used_f, total_f = fs.get_space_info_formatted()
                        print(f"Total: {total_f}, Usado: {used_f}, Livre: {free_f}")
                        arquivos = fs.list_files()
                        if arquivos:
                            print(f"Itens ({len(arquivos)}):")
                            for arq in arquivos:
                                timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(arq.get('timestamp', 0)))
                                protected = " [P]" if arq.get('protected', False) else ""
                                item_type = "[DIR]" if arq['type'] == 1 else "[ARQ]"
                                if arq['type'] == 1:
                                    size_info = f"({fs._format_size(arq.get('calculated_size', 0))})" if arq.get('calculated_size', 0) > 0 else "(vazio)"
                                else:
                                    size_info = f"({fs._format_size(arq['size'])})"
                                print(f"  {item_type} {arq['name']} {size_info} {timestamp}{protected}")
                else:
                    print("Arquivo não encontrado")

            elif opcao in ['3', '4', '5', '6', '7', '8', '9', '10', '11', '12', '13']:
                if not fs.filename:
                    print("Nenhum sistema carregado")
                    continue

                if opcao == '3':
                    origem = input("Arquivo origem: ")
                    destino = input("Nome no FS (Enter=mesmo): ").strip()
                    fs.copy_to_fs(origem, destino if destino else None)
                elif opcao == '4':
                    origem = input("Arquivo no FS: ")
                    destino = input("Destino: ")
                    fs.copy_from_fs(origem, destino)
                elif opcao == '5':
                    antigo = input("Nome atual: ")
                    novo = input("Novo nome: ")
                    fs.rename_file(antigo, novo)
                elif opcao == '6':
                    nome = input("Arquivo: ")
                    if input(f"Remover '{nome}'? (s/N): ").lower() == 's':
                        fs.remove_file(nome)
                elif opcao == '7':
                    arquivos = fs.list_files()
                    print(f"DEBUG: Encontrados {len(arquivos)} itens no diretório atual (bloco {fs.current_directory})")
                    if arquivos:
                        print(f"{'Tipo':<6} {'Nome':<20} {'Tamanho':<25} {'P':<2} {'Data':<20}")
                        print("-" * 73)
                        for arq in arquivos:
                            timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(arq.get('timestamp', 0)))
                            protected = "S" if arq.get('protected', False) else "N"
                            item_type = "[DIR]" if arq['type'] == 1 else "[ARQ]"
                            if arq['type'] == 1:
                                size_info = fs._format_size(arq.get('calculated_size', 0)) if arq.get('calculated_size', 0) > 0 else "vazio"
                            else:
                                size_info = fs._format_size(arq['size'])
                            print(f"{item_type:<6} {arq['name']:<20} {size_info:<25} {protected:<2} {timestamp}")
                    else:
                        print("Nenhum item encontrado")
                elif opcao == '8':
                    free_f, used_f, total_f = fs.get_space_info_formatted()
                    print(f"Total: {total_f}, Usado: {used_f}, Livre: {free_f}")
                elif opcao == '9':
                    nome = input("Nome: ")
                    fs.toggle_protection(nome)
                elif opcao == '10':
                    nome = input("Nome do diretório: ")
                    fs.create_directory(nome)
                elif opcao == '11':
                    nome = input("Diretório (.. para voltar): ")
                    fs.change_directory(nome)
                elif opcao == '12':
                    nome = input("Diretório a remover: ")
                    if input(f"Remover '{nome}'? (s/N): ").lower() == 's':
                        fs.remove_directory(nome)
                elif opcao == '13':
                    antigo = input("Nome atual: ")
                    novo = input("Novo nome: ")
                    fs.rename_directory(antigo, novo)

            elif opcao == '0':
                fs.close()
                print("Sistema fechado!")
                break
            else:
                print("Opção inválida")

        except KeyboardInterrupt:
            fs.close()
            print("\nSistema fechado.")
            break
        except Exception as e:
            print(f"Erro: {e}")


if __name__ == "__main__":
    main()