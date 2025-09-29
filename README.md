FURGfs3 - Sistema de Arquivos Acadêmico
📋 Descrição
O FURGfs3 é um sistema de arquivos virtual desenvolvido em Python que reside inteiramente dentro de um único arquivo. Implementa conceitos de sistemas de arquivos como FAT (Tabela de Alocação de Arquivos), diretórios hierárquicos e operações básicas de arquivos.

✨ Características
✅ Sistema de arquivos FAT residente em arquivo único

✅ Suporte a diretórios hierárquicos

✅ Operações completas de arquivos (criar, copiar, renomear, remover)

✅ Proteção de arquivos contra escrita/remoção

✅ Verificação de integridade com hash MD5

✅ Cálculo de espaço livre/utilizado

✅ Interface de menu interativa

🛠️ Requisitos
Python 3.6 ou superior

Sistema operacional Windows (testado), mas compatível com outros

📥 Instalação e Execução
Salve o código em um arquivo chamado furgfs3.py

Execute o programa:

bash
python furgfs3.py
🎮 Como Usar
Menu Principal
text
=== FURGfs3 [/] ===
1. Criar sistema
2. Abrir sistema
3. Copiar para FS
4. Copiar do FS
5. Renomear arquivo
6. Remover arquivo
7. Listar
8. Espaço
9. Proteger/Desproteger
10. Criar dir
11. Entrar dir
12. Remover dir
13. Renomear dir
14. Verificar integridade
0. Sair
Operações Principais
1. Criar Sistema de Arquivos
Cria um novo sistema FURGfs3

Define o tamanho (1MB - 10GB)

Cria automaticamente o arquivo autores.txt com informações da equipe

2. Abrir Sistema Existente
Carrega um sistema FURGfs3 previamente criado

Mostra informações de espaço e lista arquivos

3. Copiar Arquivo para o FS
Copia arquivos do sistema real para o FURGfs3

Suporte a caminhos com espaços: use aspas "C:\caminho\com espaços\arquivo.txt"

Verificação automática de integridade com MD5

4. Copiar Arquivo do FS
Copia arquivos do FURGfs3 para o sistema real

Verificação automática de integridade

5-6. Gerenciar Arquivos
Renomear e remover arquivos

Arquivos protegidos não podem ser removidos/renomeados

7. Listar Conteúdo
Mostra arquivos e diretórios do diretório atual

Exibe tamanhos, datas e status de proteção

8. Informações de Espaço
Mostra espaço total, utilizado e livre

9. Proteger/Desproteger
Alterna proteção de arquivos/diretórios contra modificação

10-13. Gerenciar Diretórios
Criar, entrar, remover e renomear diretórios

Navegação hierárquica com .. para voltar

14. Verificar Integridade
Verifica manualmente a integridade de qualquer arquivo

Mostra hash MD5 e tamanho

🔧 Especificações Técnicas
Estrutura do Sistema de Arquivos
Tamanho do bloco: 1024 bytes

Tamanho máximo do nome: 32 caracteres

Tamanho do cabeçalho: 128 bytes

Tamanho da entrada de diretório: 64 bytes

Tamanho da entrada FAT: 4 bytes

Layout do Arquivo FS
text
[HEADER (128 bytes)]
[FAT (tabela de alocação)]
[DIRETÓRIO RAIZ (1 bloco)]
[DADOS (restante do espaço)]
Formato do Cabeçalho
c
struct header {
    uint32_t header_size;
    uint32_t block_size;
    uint32_t total_size;
    uint32_t fat_start;
    uint32_t root_start;
    uint32_t data_start;
    uint32_t total_blocks;
    uint32_t free_blocks;
    char signature[32];
};
🧪 Testes de Integridade
O sistema implementa verificação de integridade automática:

Hash MD5 em todas as operações de cópia

Verificação automática ao copiar para/do FS

Detecção de corrupção com remoção de arquivos corrompidos

Verificação manual via opção 14 do menu

Exemplo de saída de verificação:
text
Hash MD5 do arquivo original: d41d8cd98f00b204e9800998ecf8427e
Hash MD5 após cópia para FS: d41d8cd98f00b204e9800998ecf8427e
✅ Integridade verificada: arquivo copiado sem corrupção
👥 Autores
henrique bertochi grigol - 162647 - henriquebg.bg@furg.br

vicenzo copetti - 164433 - vicenzocopetti@furg.br

tiago pinheiro - 162649 - tiagopinheiro@furg.br

⚠️ Observações Importantes
Arquivos .fs: São criados na mesma pasta do script Python

Proteção: Arquivos protegidos não podem ser removidos ou renomeados

Integridade: Sempre verifique a integridade após operações críticas

Backup: Mantenha cópias importantes fora do FURGfs3

Performance: Arquivos muito grandes podem demorar para copiar

🔍 Solução de Problemas
Erro: "Arquivo não encontrado"
Verifique se o sistema de arquivos foi criado/carregado

Confirme o caminho do arquivo .fs

Erro: "Espaço insuficiente"
O sistema está cheio

Delete arquivos não necessários ou crie um sistema maior

Erro de Integridade
O arquivo pode ter sido corrompido durante a cópia

Tente copiar novamente ou use a verificação manual

📄 Licença
Projeto acadêmico desenvolvido para a disciplina de Sistemas Operacionais da FURG.