---
name: seo-automation
description: Automates execution of SEO strategies from PipelineFace for Studio Githa using Chrome DevTools MCP and PostgreSQL business context.
---

# SEO Automation Skill — Studio Githa & PipelineFace

Esta skill orienta agentes IA na execução automatizada de estratégias de SEO catalogadas no **PipelineFace**, utilizando os dados reais de negócio do **Studio Githa** (PostgreSQL) como fonte da verdade e o **Chrome DevTools MCP** como motor de execução no navegador.

---

## 🎯 Visão Geral do Fluxo

```
1. Pesquisar & Auditar o que já foi implementado (manage_seo_knowledge.py --implemented)
2. Obter Prioridades Pendentes e Escolher a Estratégia (manage_seo_knowledge.py --pending)
3. Marcar Imediatamente como EM_ANDAMENTO (manage_seo_knowledge.py --in-progress <basename>)
4. Gerar Plano Enriquecido & Carregar Dados (/api/seo/execution-plan/{basename})
5. Executar Ações no Browser via Chrome DevTools MCP / WordPress REST API
6. Atualizar Progresso Final como COMPLETED (manage_seo_knowledge.py --mark <basename>)
```

---

## 📋 Passo a Passo Operacional

### 1. Pesquisar o Que Já Foi Implementado & Auditar o Estado Atual
Antes de planejar ou executar qualquer nova ação, o agente DEVE pesquisar o histórico de implementações para obter contexto completo do que já foi feito e identificar exatamente o que falta fazer:

1. **Consultar Estratégias já Concluídas no PipelineFace**:
   - **Via CLI**: `python3 scripts/SEO/manage_seo_knowledge.py --implemented`
   - **Via API REST**: `GET http://localhost:8000/api/seo/priorities?status=completed`
   - **Ver Detalhes e Notas de Execução**: `python3 scripts/SEO/manage_seo_knowledge.py --detail <BASENAME>`
   - **Objetivo**: Identificar quais procedimentos, palavras-chave de foco, páginas e schemas já foram implementados e quais notas de auditoria foram registradas.

2. **Auditar o Estado Real no Navegador & Catálogo Local (`SiteStudioGitha/`)**:
   - **Sincronização Local Rápida**:
     ```bash
     python3 SiteStudioGitha/backup_pages.py
     ```
     Baixa e atualiza todas as páginas (publicadas e rascunhos) em arquivos HTML editáveis dentro de `SiteStudioGitha/pages/`.
   - **WordPress (`https://studiogitha.com/wp-admin/edit.php?post_type=page`)**:
     - Conferir os slugs/URLs já utilizados (ex: `/limpeza-de-pele-em-bh/`) para não duplicar rotas.
     - Conferir o score do Rank Math das páginas existentes.
   - **Google Search Console**:
     - Verificar se as URLs criadas anteriormente já foram submetidas ou indexadas.

3. **Mapear Lacunas e Escolher Próxima Ação**:
   - Comparar o catálogo de serviços do Studio Githa com o que já foi publicado.
   - Selecionar a próxima estratégia pendente de maior impacto.

### 2. Obter Prioridades Pendentes e Contexto do Studio Githa
- Chamar `python3 scripts/SEO/manage_seo_knowledge.py --pending` (ou endpoint `GET http://localhost:8000/api/seo/priorities?status=pending`) para listar apenas as estratégias pendentes.
- O sistema cruza os serviços mais rentáveis/demandados do Githa (ex: *Design de Sobrancelhas*, *Limpeza de Pele*, *Extensão de Cílios*) com os pilares de SEO Local, On-Page e GEO.

### 3. Marcar Imediatamente a Estratégia como EM_ANDAMENTO (In Progress)
> [!IMPORTANT]
> **Regra Obrigatória:** Assim que uma dica/estratégia for escolhida para execução com o usuário, o agente DEVE marcar seu status imediatamente como `in_progress` (`EM_ANDAMENTO`) no MongoDB antes de começar a codificar, editar páginas ou disparar ações no navegador. Isso evita que estratégias em execução se misturem com as que ainda faltam implementar.

- **Comando Obrigatório via CLI**:
  ```bash
  python3 scripts/SEO/manage_seo_knowledge.py --in-progress <BASENAME> --notes "Iniciando implementação da estratégia..."
  ```

### 4. Carregar o Plano de Execução Enriquecido
- Chamar `GET http://localhost:8000/api/seo/execution-plan/{basename}`.
- Cada passo retorna:
  - `action_type`: `browser_action` | `llm_generatable` | `data_enrichable` | `manual_only`
  - `target_tool`: `wordpress_wpadmin` | `google_search_console` | `google_my_business` | `ga4` | `bing_webmaster`
  - `suggested_inputs`: Variáveis pré-populadas (endereço, telefone, serviços top, etc.)

---

## 🌐 Mapeamento de Execução por Ferramenta (Chrome DevTools MCP)

### A. WordPress Admin (`https://studiogitha.com/wp-admin`)

#### 1. Criação e Identidade Visual da Página:
1. `navigate_page(url="https://studiogitha.com/wp-admin/post-new.php?post_type=page")`
2. **Modelo da Página (Template)**:
   - Configurar o atributo de modelo como `elementor_canvas` ou `elementor_header_footer`.
3. **Identidade Visual Oficial do Studio Githa**:
   - Fundo Dark Luxury (`#121614` com degradê radial `#2a332d`).
   - Tipografia oficial: `Outfit` (títulos H1/H2 e botões), `Livvic` (subtítulos) e `Inter` (corpo e detalhes).
   - Acentos de cor da marca: Rosê/Gold (`#fdafe1`).
   - Cards com efeito Glassmorphism (`rgba(33, 41, 36, 0.75)`, bordas arredondadas de 20px).
   - Botões CTA em formato pílula (`border-radius: 30px`, gradiente `#fdafe1` a `#e085c2`, texto escuro em caixa alta) com link direto para WhatsApp com mensagem personalizada.
4. **Status Seguro**: Salvar inicialmente como **Rascunho (Draft)** (`wp.data.dispatch('core/editor').savePost()`) para garantir reversibilidade (rollback).

#### 2. Protocolo Obrigatório de Otimização de SEO On-Page (Rank Math):
Toda nova página de serviço desenvolvida no WordPress DEVE cumprir a seguinte checklist para atingir pontuação **>= 80/100 (Verde)** no Rank Math:

1. **Definição da Palavra-Chave de Foco (Focus Keyword)**:
   - Identificar o termo local de maior intenção de busca (ex: `limpeza de pele em bh`, `design de sobrancelhas em bh`).
   - Inserir no campo de palavra-chave do Rank Math (`.rank-math-focus-keyword-field input`).
2. **Otimização do Snippet (Título de SEO & Meta Descrição)**:
   - **Título de SEO (Meta Title)**: Deve iniciar com a palavra-chave de foco, conter um número e a marca Studio Githa (ex: `[Palavra-Chave]: 7 Benefícios e Protocolo | Studio Githa`). Tamanho ideal: 50–60 caracteres.
   - **Meta Descrição**: Deve conter a palavra-chave nos primeiros termos, citar a localização (*Nova Suíça, Belo Horizonte*) e incluir um Call-To-Action (ex: `Procurando [Palavra-Chave]? Conheça o protocolo exclusivo do Studio Githa no Nova Suíça. Agende pelo WhatsApp!`). Tamanho ideal: 140–160 caracteres.
   - **Slug / URL Amigável**: Conter exatamente a palavra-chave em formato kebab-case (ex: `/limpeza-de-pele-em-bh/`).
3. **Estrutura Semântica, Naturalidade do Texto e Extensão**:
   - **Regra de Redação Local (Uso Único de 'em BH')**:
     - O título principal `<h1>` deve ser limpo e elegante: `<Procedimento>: <Subtítulo/Benefício>` (ex: `Brow Lamination: Sobrancelhas Encorpadas`, `Design de Sobrancelhas: Visagismo e Precisão`).
     - A palavra-chave regional com *"em BH"* deve aparecer **apenas 1 ÚNICA VEZ** no subtítulo do primeiro parágrafo (hero) para garantir a indexação local do Google e Rank Math.
     - **NÃO repetir 'em BH'** nos títulos `<h2>`, cards, passos, botões ou FAQ. O texto deve soar 100% natural, sofisticado e humanizado, mantendo a menção geográfica concentrada nas informações de rodapé/endereço (*Nova Suíça, Belo Horizonte - MG*).
   - **Extensão**: Mínimo de 600 a 800 palavras bem estruturadas.
   - **Texto Alternativo (Alt Text) em Imagens**: Incluir imagem com `alt="[Procedimento] no Studio Githa"`.
   - **Seção de FAQ Estruturada**: Incluir pelo menos 3 perguntas e respostas frequentes para captura de Snippets e IA Search (Perplexity, ChatGPT Search, Google SGE).
4. **Validação e Extração da Pontuação (Script Obrigatório)**:
   - Para verificar a nota exata do Rank Math durante a edição no WordPress Gutenberg, execute via `evaluate_script`:
   ```javascript
   (() => {
     // 1. Extrair do elemento visual do DOM do Rank Math
     const scoreEl = document.querySelector('.rank-math-toolbar-score .score-text') || 
                     document.querySelector('.rank-math-score') ||
                     document.querySelector('.seo-score .score-text');
     const scoreText = scoreEl ? scoreEl.innerText.trim() : 'N/A';
     const scoreNum = scoreText.includes('/') ? parseInt(scoreText.split('/')[0].trim(), 10) : null;
     
     // 2. Extrair classe de status (good = verde, ok = amarelo, bad/bad-fk = vermelho)
     const seoScoreContainer = document.querySelector('.rank-math-toolbar-score .seo-score') || 
                               document.querySelector('.seo-score') ||
                               document.querySelector('.rank-math-toolbar-score');
     const statusClass = seoScoreContainer ? seoScoreContainer.className : '';
     
     // 3. Extrair do Redux Store oficial do WordPress
     const reduxScore = window.wp?.data?.select('rank-math')?.getAnalysisScore ? 
                        window.wp.data.select('rank-math').getAnalysisScore() : null;
     const keywords = window.wp?.data?.select('rank-math')?.getKeywords ? 
                      window.wp.data.select('rank-math').getKeywords() : '';
     
     return {
       scoreText,      // Ex: "85 / 100" ou "19 / 100"
       scoreNum,       // Ex: 85 ou 19
       isGreen: scoreNum !== null ? scoreNum >= 80 : false,
       statusClass,    // Ex: "seo-score good" ou "seo-score bad-fk"
       reduxScore,     // Pontuação numérica interna
       keywords        // Palavra-chave de foco cadastrada
     };
   })()
   ```
   - **Se o score for < 80 ou estiver com classe `bad-fk`**:
     Injetar a palavra-chave via store do Rank Math:
     ```javascript
     window.wp.data.dispatch('rank-math').updateKeywords('<PALAVRA_CHAVE_DE_FOCO>');
     window.wp.data.dispatch('core/editor').savePost();
     ```

#### 3. Inserir Schema.org JSON-LD LocalBusiness:
1. Utilizar dados da clínica (`BeautySalon`, endereço `Rua Juraci, 88 - Sala 102`, telefone, horários).
2. O Rank Math injeta automaticamente via módulo *SEO Local* configurado globalmente.

### B. Google Search Console (`https://search.google.com/search-console`)
- **Solicitar Indexação**:
  1. `navigate_page(url="https://search.google.com/search-console")`
  2. Inspecionar URL da nova página criada.
  3. Clicar em *"Testar URL ao vivo"* e em seguida *"Solicitar indexação"*.
- **Auditar Consultas Posição 4-15**:
  1. Filtrar desempenho por posições de oportunidade e correlacionar com procedimentos do Githa.

### C. Google Meu Negócio / Google Business Profile
- **Atualizar Serviços e Horários**:
  1. Sincronizar catálogo de serviços com nomes e preços do PostgreSQL do Githa.
  2. Criar posts de atualização com novidades e procedimentos em destaque.

### D. Google Analytics (GA4)
- **Filtro de Tráfego de IAs**:
  1. `navigate_page` no GA4 > Relatórios > Aquisição de Tráfego.
  2. Criar filtro para identificar tráfego vindo de `chatgpt.com`, `perplexity.ai`, `claude.ai`.

---

## 🛠️ Scripts Auxiliares Python (`scripts/SEO/`)

Para evitar erros de sintaxe ou de atributos, utilize sempre os scripts utilitários prontos:

### 1. Consultar Serviços e Preços Reais do Githa (PostgreSQL):
```bash
python3 scripts/SEO/get_githa_services.py
```
* **O que faz**: Carrega o contexto oficial de serviços, preços (`s.price`), durações (`s.duration_minutes`), descrições e total de agendamentos (`s.appointment_count`).

### 2. Criar e Publicar Páginas no WordPress via REST API:
```bash
python3 scripts/SEO/create_wp_page.py \
  --title "Nome da Página" \
  --slug "slug-da-pagina" \
  --status draft \
  --file caminho/para/pagina.html
```
* **O que faz**: Autentica de forma segura no WordPress com as credenciais do `.env`, injeta o HTML e cria a página em modo Rascunho (`draft`) ou Publicado (`publish`) com template `elementor_canvas`.

### 3. Gerenciar, Auditar e Listar Estratégias SEO (MongoDB `seo_knowledge`):
```bash
# Listar todas as estratégias e status:
python3 scripts/SEO/manage_seo_knowledge.py --list

# Listar somente diretrizes permanentes (Core Standards):
python3 scripts/SEO/manage_seo_knowledge.py --core-rules

# Promover uma estratégia para Core Standard permanente:
python3 scripts/SEO/manage_seo_knowledge.py --set-core <BASENAME> --scope "all_pages,on_page_structure"

# Registrar a aplicação de um Core Standard em uma página:
python3 scripts/SEO/manage_seo_knowledge.py --apply-core <BASENAME> --page lash-lifting-em-bh --page-id 334 --notes "Estrutura H1/H2/H3 aplicada."

# Listar somente estratégias já concluídas (com notas de auditoria):
python3 scripts/SEO/manage_seo_knowledge.py --implemented

# Listar somente estratégias pendentes de implementação:
python3 scripts/SEO/manage_seo_knowledge.py --pending

# Inspecionar detalhes e passos de uma estratégia específica:
python3 scripts/SEO/manage_seo_knowledge.py --detail <BASENAME>

# Marcar uma estratégia individual pontual como concluída (Regra 1 a 1):
python3 scripts/SEO/manage_seo_knowledge.py --mark post_28063324779927810 --steps 0,1,2,3,4 --notes "Página criada no WordPress com Rank Math 81/100, Schema LocalBusiness configurado e URL pronta."
```

---

## 📁 Gestão e Edição Local de Páginas (`SiteStudioGitha/`)

Para acelerar a criação, revisão de copy e manutenção do design Dark Luxury, todas as páginas do WordPress podem ser editadas diretamente no computador e sincronizadas bidirecionalmente com o WordPress:

### Estrutura do Diretório:
```
SiteStudioGitha/
├── pages/                  # Arquivos .html individuais prontos para edição local
├── json/                   # Payload JSON bruto completo de cada página
├── manifest.json           # Metadados e índices de mapeamento das páginas
├── README.md               # Tabela de páginas com links diretos de edição no WP
├── backup_pages.py         # Baixa/sincroniza todas as páginas do site
└── push_page.py            # Envia a página editada de volta para o WordPress
```

### Comandos de Sincronização:

1. **Baixar/Atualizar Todas as Páginas do WordPress**:
   ```bash
   python3 SiteStudioGitha/backup_pages.py
   ```
   *Baixa todas as páginas (publicadas e rascunhos), atualiza o `manifest.json` e gera o `README.md` com a tabela atualizada.*

2. **Enviar Página Editada Localmente de Volta para o WordPress**:
   ```bash
   # Envia as alterações preservando o status atual:
   python3 SiteStudioGitha/push_page.py --file SiteStudioGitha/pages/limpeza-de-pele-em-bh.html

   # Envia alterando o status para publicado:
   python3 SiteStudioGitha/push_page.py --file SiteStudioGitha/pages/limpeza-de-pele-em-bh.html --status publish
   ```

---

## 📝 Registro e Auditoria de Execução

### ⚠️ Regra Fundamental: Execução e Marcação Individual (UMA em UMA)
- **NUNCA** marcar estratégias em lote na collection `seo_knowledge`.
- Cada ciclo de automação deve focar em **UMA única estratégia** específica por vez.
- O registro de aplicação (`user_implementation`) deve ser feito individualmente para aquela estratégia específica, detalhando exatamente quais passos foram concluídos, notas de auditoria e data/hora (`applied_at`).

### Procedimento de Atualização:
Após a execução dos passos no navegador para a estratégia ativa:
1. Executar o script auxiliar de marcação:
   ```bash
   python3 scripts/SEO/manage_seo_knowledge.py --mark <BASENAME> --steps 0,1,2,3,4 --notes "<DESCRICAO_DETALHADA>"
   ```
2. Ou chamar o endpoint `POST http://localhost:8000/api/seo/mark-applied/{basename}` enviando:
```json
{
  "step_indices": [0, 1, 2, 3, 4],
  "notes": "Página criada no WordPress com Rank Math >= 80/100, Schema LocalBusiness e link associado."
}
```
3. Tirar screenshot de evidência via `take_screenshot()` se necessário para comprovação.

