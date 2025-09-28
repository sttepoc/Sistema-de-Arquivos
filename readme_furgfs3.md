# FURGfs3 - Sistema de Arquivos Virtual

**Trabalho prático da disciplina de Sistemas Operacionais**

## 👥 Autores
- **Henrique Bertochi Grigol** - 162647 - henriquebg.bg@furg.br
- **Vicenzo Copetti** - 164433 - vicenzocopetti@furg.br  
- **Tiago Pinheiro** - 162649 - tiagopinheiro@furg.br

## 📋 Descrição

O FURGfs3 é um sistema de arquivos virtual implementado em Python que reside inteiramente dentro de um único arquivo `.fs` armazenado no sistema de arquivos real. O projeto simula o funcionamento de um sistema de arquivos completo, incluindo conceitos como FAT (File Allocation Table), hierarquia de diretórios e operações sobre arquivos.

### 🎯 Características Principais

- **Arquivo único**: Todo o sistema de arquivos fica contido em um arquivo `.fs`
- **FAT (File Allocation Table)**: Implementa uma tabela de alocação para gerenciar blocos
- **Hierarquia de diretórios**: Suporte completo a diretórios e subdiretórios
- **Verificação de integridade**: Utiliza SHA256 para garantir a integridade dos arquivos
- **Proteção de arquivos**: Sistema de proteção contra remoção/modificação
- **Interface amigável**: Utiliza pandas para exibir informações em formato tabular

## 🛠️ Tecnologias Utilizadas

- **Python 3.x**
- **pandas** - Para exibição de dados em formato tabular
- **pickle** - Para serialização de metadados
- **hashlib** - Para verificação de integridade (SHA256)

## 📦 Dependências

```bash
pip install pandas
```

## 🚀 Como Usar

### Execução Rápida (Demo)
```bash
python furgfs3.py
```
Este comando executa uma demonstração completa do sistema, criando um FS de 50MB e testando todas as funcionalidades.

### Uso Programático
```python
from furgfs3 import FURGfs3

# Criar novo sistema de arquivos
fs = FURGfs3("meu_fs.fs")
fs.create_fs(size_mb=100, block_size=4096)

# Ou carregar existente
fs = FURGfs3("meu_fs.fs")
fs.mount()

# Operações básicas
fs.mkdir("/documentos")
fs.copy_in("arquivo.txt", "/documentos/")
fs.ls("/documentos")
fs.space_info()
fs.unmount()
```

## 📋 Funcionalidades Implementadas

### ✅ Requisitos Obrigatórios
- [x] **Criar FURGfs3** - Criação de sistema de arquivos com tamanho definido pelo usuário
- [x] **Copiar para dentro** - Cópia de arquivos do sistema real para o FS virtual
- [x] **Copiar para fora** - Cópia de arquivos do FS virtual para o sistema real
- [x] **Renomear arquivos** - Renomeação e movimentação de arquivos/diretórios
- [x] **Remover arquivos** - Remoção de arquivos com verificação de proteção
- [x] **Listar arquivos** - Listagem de conteúdo de diretórios
- [x] **Espaço livre** - Exibição de espaço livre vs total do sistema
- [x] **Proteção de arquivos** - Sistema de proteção contra escrita/remoção
- [x] **Verificação de integridade** - Garantia de que arquivos não sejam corrompidos

### ✅ Funcionalidades Extras
- [x] **Hierarquia de diretórios** - Suporte completo a diretórios aninhados
- [x] **Criar/remover diretórios** - Operações mkdir/rmdir com suporte recursivo
- [x] **Navegação** - Comandos cd, pwd para navegação
- [x] **Metadados detalhados** - Informações de criação, modificação, tamanho, etc.
- [x] **Interface tabular** - Exibição de dados com pandas
- [x] **Tratamento de erros** - Validação e tratamento robusto de erros

## 🏗️ Arquitetura do Sistema

### Estrutura do Arquivo .fs
```
[Header + FAT + Diretório] [Área de Dados (Blocos)]
|------ Área Reservada ----||------ Blocos Livres ------|
```

### Componentes Principais

1. **Header**: Contém informações básicas do FS (tamanho, versão, endereços)
2. **FAT**: Tabela de alocação de arquivos (0=livre, -1=fim da cadeia, n=próximo bloco)
3. **Diretório**: Estrutura hierárquica com metadados de arquivos e pastas
4. **Área de Dados**: Blocos de tamanho fixo para armazenamento de conteúdo

### Metadados dos Arquivos
Cada entrada no sistema contém:
- Nome e caminho absoluto
- Tipo (arquivo/diretório)
- Tamanhos (bytes)
- Timestamps (criação/modificação)
- Hash SHA256 (para verificação de integridade)
- Status de proteção
- Lista de blocos alocados

## 📊 Parâmetros de Configuração

- **Tamanho do bloco**: 4096 bytes (padrão)
- **Tamanho mínimo do FS**: 1 MB
- **Blocos reservados**: Calculado automaticamente (mín. 8 ou 1% do total)
- **Tamanho máximo de arquivo**: Limitado pelo espaço disponível

## 🔧 API Principal

### Operações do Sistema
- `create_fs(size_mb, block_size)` - Cria novo FS
- `mount()` - Carrega FS existente
- `unmount()` - Salva e desmonta FS

### Operações de Diretório  
- `mkdir(path)` - Cria diretório
- `rmdir(path, recursive)` - Remove diretório
- `cd(path)` - Muda diretório atual
- `pwd()` - Mostra diretório atual
- `ls(path)` - Lista conteúdo

### Operações de Arquivo
- `copy_in(real_path, dest_path)` - Copia arquivo para dentro
- `copy_out(fs_path, dest_dir)` - Copia arquivo para fora  
- `rm(path)` - Remove arquivo
- `rename(old, new)` - Renomeia/move arquivo
- `protect(path, protect)` - Protege/desprotege arquivo

### Informações e Utilitários
- `space_info()` - Mostra espaço usado/livre
- `df()` - Lista todos os arquivos
- `stat(path)` - Informações detalhadas de um item

## 📝 Exemplo de Uso Completo

```python
from furgfs3 import FURGfs3

# Criar sistema de 100MB
fs = FURGfs3("exemplo.fs")
fs.create_fs(size_mb=100)

# Criar estrutura de diretórios
fs.mkdir("/documentos")
fs.mkdir("/documentos/trabalhos")
fs.mkdir("/imagens")

# Copiar arquivos
fs.copy_in("relatorio.pdf", "/documentos/trabalhos/")
fs.copy_in("foto.jpg", "/imagens/")

# Listar e navegar
fs.ls("/")
fs.cd("/documentos")
fs.ls(".")

# Proteger arquivo importante
fs.protect("/documentos/trabalhos/relatorio.pdf", True)

# Verificar espaço
fs.space_info()

# Salvar e fechar
fs.unmount()
```

## 🧪 Teste de Integridade

O sistema automaticamente verifica a integridade dos arquivos usando SHA256:

```python
# Ao copiar para fora, verifica automaticamente
fs.copy_out("/arquivo.txt", "./", verify_integrity=True)
# Saída: SHA256 ok? True
```

## 📁 Arquivos do Projeto

- `furgfs3.py` - Código fonte principal
- `furgfs3.fs` - Arquivo de exemplo do sistema (50MB)
- `autores.txt` - Arquivo com dados dos desenvolvedores
- `README.md` - Este arquivo

## ⚠️ Limitações Conhecidas

- Não suporte a links simbólicos
- Não implementa permissões de usuário (apenas proteção simples)
- Tamanho máximo limitado pela memória disponível para metadados
- Não suporte a compactação

## 🐛 Solução de Problemas

### Erro: "Diretório pai inexistente"
- Certifique-se de criar os diretórios pais antes de criar subdiretórios

### Erro: "Espaço insuficiente" 
- Verifique o espaço disponível com `fs.space_info()`
- Considere aumentar o tamanho do FS

### Erro: "Entrada protegida"
- Remova a proteção com `fs.protect(path, False)` antes de modificar

## 📄 Licença

Este projeto foi desenvolvido como trabalho acadêmico para a disciplina de Sistemas Operacionais da Universidade Federal do Rio Grande (FURG).

---

**Desenvolvido com ❤️ pelos alunos da FURG**