# CWD Leads: prospecção de clientes pelo Google Maps

Você digita um nicho e uma cidade (ex.: "psicólogo" + "Taguatinga, DF"), e o **CWD Leads** mostra os estabelecimentos em cards. Quem **não tem site** ou **só tem rede social** aparece primeiro, com botões para WhatsApp, Instagram, site e Google Maps.

Funciona de dois jeitos:
- **No seu computador** (Parte B).
- **Na internet, pela Vercel**, para usar no celular de qualquer lugar, com senha (Parte C).

---

## Parte A: criar a chave da API no Google Cloud

1. Acesse **https://console.cloud.google.com** e entre com seu Gmail.
2. **Crie um projeto:** seletor de projetos → **Novo projeto** → dê um nome (ex.: `prospeccao-clientes`) → **Criar**.
3. **Ative o faturamento:** menu ☰ → **Faturamento** → vincule uma conta (cartão). O Google exige o cartão mesmo para usar a parte gratuita.
4. **Ative a API:** **APIs e serviços → Biblioteca** → pesquise **Places API (New)** (com "(New)") → **Ativar**.
5. **Crie a chave:** **APIs e serviços → Credenciais → + Criar credenciais → Chave de API**. Ela começa com `AIza...`.
6. **Restrinja a chave:** clique na chave → **Restrições de API → Restringir chave** → selecione só a **Places API (New)** → **Salvar**.
7. **Alerta de gastos:** **Faturamento → Orçamentos e alertas → Criar orçamento** (ex.: R$ 10). O alerta só avisa por e-mail; não bloqueia nada.

### Quanto custa?
- O sistema usa **só o Text Search (New)** e pede apenas os campos que aparecem na tela. Isso entra na categoria **Text Search Enterprise**:
  - **1.000 consultas grátis por mês**;
  - depois, cerca de **US$ 35 a cada 1.000**.
- **Cada 20 resultados = 1 consulta.**
- **Travas do sistema:**
  - `LIMITE_DIARIO` (padrão **30**) e `LIMITE_MENSAL` (padrão **900**);
  - no terminal, no máximo 30 consultas por execução.
- Os preços podem mudar: https://developers.google.com/maps/billing-and-pricing/pricing

---

## Parte B: usar no computador (Windows)

1. Abra a pasta `prospect-client` no Explorador → botão direito num espaço vazio → **Abrir no Terminal**.
2. Na primeira vez:
   ```powershell
   py -m venv .venv
   .venv\Scripts\python -m pip install -r requirements.txt
   copy .env.example .env
   notepad .env
   ```
   Pule o primeiro comando se a pasta `.venv` já existir. No Bloco de Notas, cole a sua chave em `GOOGLE_PLACES_API_KEY=` e salve.
3. Para abrir:
   ```powershell
   .venv\Scripts\python cwd_leads.py
   ```
   - O navegador abre em **http://127.0.0.1:8000**.
   - Deixe o terminal aberto enquanto usa. **Ctrl+C** desliga.

**Login no computador:**
- Sem `SENHA_ACESSO` no `.env`, o sistema não pede senha. O servidor só aceita acessos do próprio computador.
- Se quiser pedir senha também no PC, preencha `SENHA_ACESSO` no `.env`.

**Contador no computador:** fica no arquivo `uso_api.json`, separado do contador da Vercel.

---

## Parte C: publicar na Vercel (usar no celular, de qualquer lugar)

### C1. Antes de tudo: o que NÃO vai para o GitHub
O `.gitignore` já impede que estes itens subam:
- `.env`, com a sua chave;
- `.venv/`;
- `resultados/`;
- `uso_api.json`;
- `.vercel/`.

Para conferir, rode na pasta do projeto:
```powershell
git status
```
Nenhum desses nomes pode aparecer na lista. A chave do Google, a senha e o segredo **nunca** vão para o código: ficam só nas variáveis de ambiente da Vercel.

### C2. Criar a senha e o segredo
- **Senha de acesso (`SENHA_ACESSO`):**
  - Escolha uma com **12 caracteres ou mais**, ou gere uma com o comando abaixo.
  - Guarde num gerenciador de senhas.
  ```powershell
  .venv\Scripts\python -c "import secrets; print(secrets.token_urlsafe(12))"
  ```
- **Segredo da sessão (`SEGREDO_SESSAO`):**
  - É um texto aleatório que assina o cookie de login. Você nunca vai digitar esse texto.
  - Gere com:
  ```powershell
  .venv\Scripts\python -c "import secrets; print(secrets.token_urlsafe(32))"
  ```

### C3. Enviar o projeto para o GitHub (repositório PRIVADO)
1. Entre em **https://github.com/new**.
2. Nome: `cwd-leads`. Marque **Private** e não adicione README nem .gitignore.
3. Clique em **Create repository**.
4. No terminal, na pasta do projeto, troque `SEU-USUARIO` pelo seu usuário do GitHub:
   ```powershell
   git remote add origin https://github.com/SEU-USUARIO/cwd-leads.git
   git branch -M main
   git push -u origin main
   ```
   Na primeira vez, o Git abre o navegador para você entrar no GitHub.

### C4. Criar o projeto na Vercel
1. Entre em **https://vercel.com** → **Sign Up / Log In** com a conta do GitHub.
2. **Add New… → Project** → ao lado do repositório `cwd-leads`, clique em **Import**.
3. Em **Framework Preset**, confira se aparece **FastAPI**.
4. Abra **Environment Variables** e cadastre:

   | Name | Value |
   |---|---|
   | `GOOGLE_PLACES_API_KEY` | sua chave do Google (`AIza...`) |
   | `SENHA_ACESSO` | sua senha (12+ caracteres) |
   | `SEGREDO_SESSAO` | o texto gerado no passo C2 |
   | `LIMITE_DIARIO` | `30` (opcional) |
   | `LIMITE_MENSAL` | `900` (opcional) |

5. Clique em **Deploy**.

Ao abrir o site agora, ele avisa que o **Upstash Redis não está conectado**. Isso é esperado: é a trava de segurança. O próximo passo resolve.

> **Dica de segurança:** em **Settings → Environment Variables**, deixe essas variáveis só no ambiente **Production** e marque-as como **Sensitive**. Assim, versões de teste (Preview) ficam bloqueadas, porque não têm senha, e ninguém consegue ler os valores depois de salvos.

### C5. Conectar o Upstash Redis (contador e bloqueio de senha)
1. No projeto da Vercel, abra a aba **Storage** → **Create Database**, ou **Browse Marketplace** → **Upstash** → **Redis**.
2. Escolha o plano **Free** e a região mais perto (ex.: São Paulo, se houver).
3. Conecte ao projeto `cwd-leads`. A Vercel cria sozinha as variáveis `UPSTASH_REDIS_REST_URL` e `UPSTASH_REDIS_REST_TOKEN`. Nomes antigos, `KV_REST_API_URL` e `KV_REST_API_TOKEN`, também funcionam.
4. Vá em **Deployments** → no último deploy, **⋯ → Redeploy**. Mudanças em variáveis só valem num deploy novo.

O plano grátis do Upstash tem 500 mil comandos por mês; cada busca usa poucos.

### C6. Conferir se está seguro (2 minutos)
Abra o endereço da Vercel (ex.: `https://cwd-leads.vercel.app`) numa **janela anônima**:
- [ ] A tela de login aparece.
- [ ] `https://SEU-ENDERECO/api/uso` mostra erro **401** ("Faça login").
- [ ] `https://SEU-ENDERECO/.env` e `https://SEU-ENDERECO/buscar_clientes.py` dão **404**.
- [ ] Depois de 5 senhas erradas, aparece "Muitas senhas erradas. Tente de novo em 15 min."
- [ ] Com a senha certa, você entra, e uma busca de **20 resultados** gasta **1** consulta no contador.

### C7. Instalar no celular
1. Abra o endereço no celular e faça login.
2. Instale o app:
   - **Android (Chrome):** toque em **Instalar** no aviso do app, ou use o menu **⋮ → Instalar app**.
   - **iPhone (Safari):** toque em **Compartilhar** → **Adicionar à Tela de Início**.
3. Abra pelo ícone da CWD e faça login de novo. No iPhone, o app instalado tem login separado do Safari.

A sessão dura **30 dias** em cada aparelho. Para encerrar, use **Sair deste aparelho**, no fim da página.

### C8. Atualizar
Toda vez que você enviar mudanças com `git push`, a Vercel publica a versão nova sozinha.

### Plano gratuito da Vercel (Hobby)
Pelos termos da Vercel, o plano Hobby é para **uso pessoal e não comercial**. Uma ferramenta usada pela agência para conseguir clientes pode ser considerada uso comercial; nesse caso, o certo é o plano **Pro**. Leia e decida: https://vercel.com/docs/limits/fair-use-guidelines

---

## Como usar

- **Busca:** nicho, cidade e quantos resultados (20, 40 ou 60). No celular, depois de buscar, o formulário vira uma barra no topo; toque nela para uma nova busca.
- **Etiquetas:**
  - **Sem site:** o lugar não tem link, ou tem um site antigo `business.site` do Google, que foi desativado.
  - **Só rede social:** o link é de Instagram, Facebook, Linktree, Taplink, linkme.bio, bio.site, Beacons ou WhatsApp.
  - **Tem site:** qualquer outro link.
- **Botões:**
  - **WhatsApp:**
    - Aparece para celulares, com o selo "provável WhatsApp", ou quando o link do lugar é do WhatsApp.
    - **No celular, abre direto o app.** No Android, se o WhatsApp não estiver instalado, abre o `wa.me`.
  - **Instagram:** abre o perfil, se o link do lugar for do Instagram. Se não for, pesquisa no Google.
  - **Site:** abre o link do lugar, quando houver.
  - **Maps:** abre o lugar no Google Maps.
  - **Telefone:** no celular, toque no número para ligar.
- **Filtros:**
  - "Sem site" e "Só rede social" podem ser marcados juntos.
  - Em **Mais filtros** ficam nota mínima, avaliações mínimas e ordenação.
  - Os filtros **não gastam consultas**.
- **Nada fica guardado:** recarregar a página apaga os resultados. Isso segue a política do Google.

### Pelo terminal (opcional)
```powershell
.venv\Scripts\python buscar_clientes.py "psicólogo em Brasília" --paginas 1
```
Mostra só um resumo: quantos encontrou, quantos estão sem site e quantos só têm rede social.

---

## Segurança (como funciona)

- **Senha:** fica na variável `SENHA_ACESSO`, nunca no código. A comparação é feita de forma que o tempo de resposta não dê pistas.
- **Sessão:**
  - Cookie `HttpOnly`, que o JavaScript não lê; `Secure`, que só trafega em HTTPS; e `SameSite=Lax`.
  - Vale por 30 dias e é assinado com `SEGREDO_SESSAO`.
  - Trocar a senha ou o segredo desconecta todos os aparelhos.
- **Rotas protegidas:** sem login, `/api/buscar` e `/api/uso` respondem 401, e o Google nem é chamado.
- **Bloqueio:**
  - **5 senhas erradas do mesmo IP bloqueiam esse IP por 15 minutos.**
  - 20 erros no total, de qualquer IP, bloqueiam novos logins por 15 minutos. Quem já está logado continua usando.
- **IP usado no bloqueio:**
  - Na Vercel, vem só do cabeçalho `x-real-ip`, que a própria Vercel preenche. Ela sobrescreve os cabeçalhos de IP vindos de fora para impedir falsificação.
  - IPv6 é agrupado por bloco /64.
  - No computador, nenhum cabeçalho é aceito: vale o IP da conexão.
- **À prova de esquecimento:** se faltar senha, segredo ou Redis na Vercel, a API **bloqueia tudo** em vez de ficar aberta.
- **Proteções extras:**
  - Content-Security-Policy, para que a página só rode os scripts do próprio sistema.
  - Bloqueio de abrir a página dentro de outros sites.
  - Links externos não informam de onde você veio.

## Política do Google (Places API)

- **Logo:** sem mapa do Google na tela, é obrigatório o logo **Google Maps**. O sistema usa o oficial, sem alterações, no topo dos resultados.
- **Guardar dados:**
  - É proibido guardar dados da Places API; a exceção é o **place ID**.
  - O sistema não salva resultados.
  - O service worker do app instalado guarda só a "casca" (tela, estilo, ícones) e nunca as respostas da API.
  - O Redis guarda só contagens.
- Política completa: https://developers.google.com/maps/documentation/places/web-service/policies

---

## Erros comuns

| Mensagem | O que fazer |
|---|---|
| `chave da API não encontrada` | Computador: preencha o `.env`. Vercel: cadastre `GOOGLE_PLACES_API_KEY` e faça Redeploy. |
| `login não configurado na Vercel` | Cadastre `SENHA_ACESSO` (12+) e `SEGREDO_SESSAO` (32+) e faça Redeploy. |
| `Variável ausente: o Upstash Redis precisa de KV_REST_API_URL e KV_REST_API_TOKEN…` | Essas variáveis não chegaram ao deploy. A mensagem lista as variáveis parecidas que existem. Confira em **Settings → Environment Variables** se elas estão em **Production** e faça um novo deploy (passo C5). |
| `Variável ausente: X não existe ou está vazia (Y existe)` | Só metade do par está cadastrada. Cadastre a que falta (URL e token andam juntos). |
| `… precisa começar com https://` | Foi usada a URL `redis://` (KV_URL/REDIS_URL) no lugar da URL REST. Use `KV_REST_API_URL`. |
| `Erro ao conectar: … recusou o token` | Token errado ou o token "somente leitura". Use `KV_REST_API_TOKEN`. |
| `Erro ao conectar: não foi possível alcançar o endereço` | A URL REST está errada ou o banco foi apagado no Upstash. |
| `Muitas senhas erradas` | Espere 15 minutos. |
| `Sua sessão terminou` | Faça login de novo. Acontece depois de 30 dias ou se a senha ou o segredo mudarem. |
| `erro 403` do Google | Confira se a Places API (New) está ativada, o faturamento ativo e a restrição da chave. |
| `limite de 30 consultas por dia atingido` | Volte amanhã ou aumente `LIMITE_DIARIO`. |
| `No module named 'fastapi'` | Rode `.venv\Scripts\python -m pip install -r requirements.txt`. |
| `A porta 8000 já está em uso` | O CWD Leads já está aberto em outra janela. |
