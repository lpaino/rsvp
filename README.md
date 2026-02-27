# App de Gestão de Festa de 15 Anos

Aplicação em **Python + Flask** para gerenciar:
- Login com níveis de permissão (admin, organizador, consulta)
- Cadastro da festa
- Cadastro de fornecedores
- Cadastro de convidados
- Portal RSVP para convidados, com inclusão dinâmica de acompanhantes
- Validação em tempo real e no envio para aceitar confirmação somente de nomes que estão na lista de convidados

## Como executar

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
export ADMIN_INITIAL_PASSWORD="defina-uma-senha-forte"
python app.py
```

Acesse:
- Portal RSVP: `http://localhost:5000/portal-rsvp`
- Login administrativo: `http://localhost:5000/login`

Usuário inicial:
- usuário: `admin`
- senha: valor de `ADMIN_INITIAL_PASSWORD`

## Fluxo RSVP

1. Convidado informa seu nome.
2. Informa se terá acompanhante.
3. Se sim, adiciona quantos nomes quiser.
4. O sistema confirma apenas se **todos os nomes** estiverem no cadastro de convidados.
