# Backlog — PipelineFace

## 🔐 Automatizar a atualização da sessão do Facebook

**Contexto:** em 2026-08-07 a sessão expirou silenciosamente — o scraper rodava, catalogava 0 posts e nenhum erro era exibido (o Facebook respondia com a login-wall pública). A sessão foi restaurada manualmente extraindo os cookies do navegador do usuário via Kimi WebBridge (CDP `Network.getCookies`) e gravando `data/scraper/session/facebook_session.json`.

**O que automatizar:**
- Detectar sessão expirada antes/depois do scrape: verificar presença dos cookies `c_user` e `xs` no `facebook_session.json` e/ou detectar login-wall na página carregada (ex.: marcadores "Criar nova conta", ausência de `c_user` no contexto).
- Falhar rápido e com erro explícito (telemetria + log) em vez de catalogar 0 posts silenciosamente.
- Renovar a sessão automaticamente via WebBridge (extração de cookies do navegador real do usuário) ou alertar o usuário para refazer o login (`./scripts/scrape.sh --login`).

**Relacionado:** o container `pipelineface_scraper` foi buildado sem `pymongo` (consta em `scraper/requirements.txt`), fazendo o scraper rodar sem salvar nada no Mongo — `_init_mongo_client()` falha silencioso. Considerar logar aviso quando o Mongo estiver indisponível e rebuild da imagem do scraper.

---

## 📅 Data inicial configurável para extração (default: 2 anos atrás)

**Contexto:** em 2026-08-07 o usuário informou que só interessam posts a partir de 21/11/2025. Hoje o scraper cataloga tudo o que o scroll alcança, sem recorte temporal.

**O que fazer:**
- Adicionar parâmetro de data inicial (ex.: `--since 2025-11-21`) no scraper e/ou na configuração (`app_config`), com **default de 2 anos atrás** calculado em runtime.
- Aplicar o corte durante a catalogação: posts mais antigos que a data não são salvos; ao atingir uma sequência de posts antigos, encerrar o scroll cedo (o feed é cronológico reverso).
- Desafio: o card do feed nem sempre expõe a data no DOM — avaliar extração de timestamp (elemento de data do post, ou abrir o permalink) e definir fallback (parar após N posts consecutivos claramente antigos).
- Expor o parâmetro na UI (modal Scraper) e respeitar no `--only-new`.

---

## 🎯 Filtro temático na pipeline (ex.: SEO e marketing digital)

**Contexto:** o objetivo do projeto é replicar apenas dicas do tema de interesse (SEO/marketing digital). Hoje a pipeline processa qualquer mídia baixada, gastando Whisper/Ollama com conteúdo fora do tema.

**O que fazer:**
- Adicionar etapa de classificação temática no início do `pipeline.py`: após OCR/transcrição, perguntar ao LLM se o conteúdo é relacionado ao tema configurado (prompt/tema em `app_config`, ex.: "SEO e marketing digital").
- Conteúdo fora do tema: não gerar `seo_knowledge`; marcar o post com status próprio (ex.: `fora_do_tema` / `skipped`) e registrar em telemetria para auditoria.
- Tema deve ser configurável (não hardcoded) — campo em `app_config` editável pela UI.
- Avaliar também um pré-filtro barato por palavras-chave antes de chamar o LLM, para economizar inferência.
