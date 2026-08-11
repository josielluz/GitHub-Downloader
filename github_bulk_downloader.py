#!/usr/bin/env python3
"""
github_bulk_downloader.py
=========================

Baixa automaticamente vários repositórios do GitHub.

MODOS:

1. USUÁRIO AUTENTICADO
   Lista TODOS os repositórios aos quais o PAT tem acesso.

2. USUÁRIO ESPECÍFICO
   Lista os repositórios públicos desse usuário.
   Com PAT, também tenta acessar os recursos permitidos.

3. ORGANIZAÇÃO
   Lista os repositórios da organização aos quais
   o PAT tem acesso.

RECURSOS:

    - Repositórios públicos
    - Repositórios privados
    - Personal Access Token
    - Fine-grained PAT
    - PAT clássico
    - Paginação automática
    - Usuário autenticado
    - Usuário específico
    - Organização
    - Filtro público/privado
    - Clonagem automática
    - Atualização automática
    - Não coloca o token na URL do Git
    - Não salva o token no código
    - Resumo final
    - Continuação mesmo se um repositório falhar

REQUISITOS:

    Python 3.9+
    Git instalado

NÃO são necessárias bibliotecas externas.
Apenas a biblioteca padrão do Python.

============================================================
EXEMPLOS
============================================================

1. BAIXAR TODOS OS REPOSITÓRIOS DO USUÁRIO DO PAT

    python github_bulk_downloader.py --mine --prompt-token

------------------------------------------------------------

2. Usar MY_GITHUB_TOKEN

Linux/macOS/Termux:

    export MY_GITHUB_TOKEN="github_pat_..."

    python github_bulk_downloader.py --mine

Windows PowerShell:

    $env:MY_GITHUB_TOKEN="github_pat_..."

    python github_bulk_downloader.py --mine

------------------------------------------------------------

3. BAIXAR REPOSITÓRIOS DE UMA ORGANIZAÇÃO

    python github_bulk_downloader.py \
        --org minha-organizacao \
        --prompt-token

------------------------------------------------------------

4. BAIXAR APENAS PRIVADOS

    python github_bulk_downloader.py \
        --mine \
        --visibility private \
        --prompt-token

------------------------------------------------------------

5. BAIXAR APENAS PÚBLICOS

    python github_bulk_downloader.py \
        --mine \
        --visibility public

------------------------------------------------------------

6. USUÁRIO ESPECÍFICO

    python github_bulk_downloader.py \
        --user usuario

------------------------------------------------------------

7. ATUALIZAR REPOSITÓRIOS JÁ BAIXADOS

    python github_bulk_downloader.py \
        --mine \
        --update \
        --prompt-token

------------------------------------------------------------

8. Escolher pasta de destino

    python github_bulk_downloader.py \
        --mine \
        --output meus_repos \
        --prompt-token

============================================================
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


# ============================================================
# CONFIGURAÇÃO
# ============================================================

API_URL = "https://api.github.com"

API_VERSION = "2026-03-10"

DEFAULT_OUTPUT = Path("github_repos")


# ============================================================
# CORES / TERMINAL
# ============================================================

RESET = "\033[0m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
CYAN = "\033[96m"


def color(text: str, codigo: str) -> str:

    if not sys.stdout.isatty():
        return text

    return f"{codigo}{text}{RESET}"


# ============================================================
# API GITHUB
# ============================================================

def github_api(
    endpoint: str,
    token: str | None = None,
    params: dict | None = None
):
    """
    Faz uma requisição GET à API REST do GitHub.
    """

    if params:

        query = urllib.parse.urlencode(
            params
        )

        url = (
            f"{API_URL}"
            f"{endpoint}"
            f"?{query}"
        )

    else:

        url = (
            f"{API_URL}"
            f"{endpoint}"
        )

    headers = {
        "Accept":
            "application/vnd.github+json",

        "X-GitHub-Api-Version":
            API_VERSION,

        "User-Agent":
            "github-bulk-downloader"
    }

    if token:

        headers[
            "Authorization"
        ] = f"Bearer {token}"

    request = urllib.request.Request(
        url,
        headers=headers,
        method="GET"
    )

    try:

        with urllib.request.urlopen(
            request,
            timeout=30
        ) as response:

            dados = response.read()

            return (
                json.loads(
                    dados.decode("utf-8")
                ),
                response.headers
            )

    except urllib.error.HTTPError as exc:

        try:

            corpo = exc.read().decode(
                "utf-8",
                errors="replace"
            )

            dados = json.loads(corpo)

            mensagem = dados.get(
                "message",
                str(exc)
            )

        except Exception:

            mensagem = str(exc)

        print(
            color(
                f"❌ GitHub API "
                f"HTTP {exc.code}: {mensagem}",
                RED
            )
        )

        return None, None

    except urllib.error.URLError as exc:

        print(
            color(
                f"❌ Erro de conexão com "
                f"a API do GitHub: {exc}",
                RED
            )
        )

        return None, None

    except TimeoutError:

        print(
            color(
                "❌ Timeout ao acessar "
                "a API do GitHub.",
                RED
            )
        )

        return None, None


# ============================================================
# PAGINAÇÃO
# ============================================================

def github_api_paginated(
    endpoint: str,
    token: str | None,
    params: dict | None = None
) -> list[dict]:
    """
    Obtém todas as páginas automaticamente.

    O GitHub permite até 100 resultados por página.
    """

    resultados = []

    pagina = 1

    parametros = dict(
        params or {}
    )

    parametros["per_page"] = 100

    while True:

        parametros["page"] = pagina

        dados, _ = github_api(
            endpoint,
            token=token,
            params=parametros
        )

        if dados is None:
            return []

        if not isinstance(
            dados,
            list
        ):
            print(
                color(
                    "❌ Resposta inesperada "
                    "da API.",
                    RED
                )
            )

            return resultados

        if not dados:
            break

        resultados.extend(
            dados
        )

        print(
            f"   Página {pagina}: "
            f"{len(dados)} repositórios"
        )

        if len(dados) < 100:
            break

        pagina += 1

    return resultados


# ============================================================
# USUÁRIO AUTENTICADO
# ============================================================

def obter_usuario_autenticado(
    token: str
) -> dict | None:

    dados, _ = github_api(
        "/user",
        token=token
    )

    if dados is None:
        return None

    return dados


# ============================================================
# REPOSITÓRIOS DO USUÁRIO AUTENTICADO
# ============================================================

def listar_repositorios_autenticados(
    token: str,
    visibility: str
) -> list[dict]:

    print()
    print(
        color(
            "🔎 Procurando repositórios "
            "acessíveis pelo PAT...",
            CYAN
        )
    )

    parametros = {
        "visibility": visibility,
        "affiliation":
            "owner,collaborator,organization_member",
        "sort": "full_name",
        "direction": "asc"
    }

    return github_api_paginated(
        "/user/repos",
        token=token,
        params=parametros
    )


# ============================================================
# REPOSITÓRIOS DE ORGANIZAÇÃO
# ============================================================

def listar_repositorios_organizacao(
    organizacao: str,
    token: str | None,
    visibility: str
) -> list[dict]:

    print()
    print(
        color(
            f"🔎 Procurando repositórios "
            f"da organização: {organizacao}",
            CYAN
        )
    )

    parametros = {
        "type": "all",
        "sort": "full_name",
        "direction": "asc"
    }

    # O endpoint de organização não usa
    # visibility e type simultaneamente.
    if visibility != "all":

        parametros = {
            "type": visibility,
            "sort": "full_name",
            "direction": "asc"
        }

    return github_api_paginated(
        f"/orgs/{urllib.parse.quote(organizacao, safe='')}/repos",
        token=token,
        params=parametros
    )


# ============================================================
# REPOSITÓRIOS DE USUÁRIO
# ============================================================

def listar_repositorios_usuario(
    usuario: str,
    token: str | None,
    visibility: str
) -> list[dict]:

    print()
    print(
        color(
            f"🔎 Procurando repositórios "
            f"do usuário: {usuario}",
            CYAN
        )
    )

    parametros = {
        "sort": "full_name",
        "direction": "asc"
    }

    # Para usuários específicos, sem autenticação
    # o GitHub retorna apenas recursos públicos.
    if visibility in (
        "public",
        "private"
    ):

        parametros["type"] = visibility

    else:

        parametros["type"] = "all"

    return github_api_paginated(
        f"/users/{urllib.parse.quote(usuario, safe='')}/repos",
        token=token,
        params=parametros
    )


# ============================================================
# NORMALIZAÇÃO DOS REPOSITÓRIOS
# ============================================================

def normalizar_repositorios(
    repositorios: list[dict],
    visibility: str
) -> list[dict]:

    resultado = []

    vistos = set()

    for repo in repositorios:

        nome = repo.get(
            "full_name"
        )

        if not nome:
            continue

        privado = bool(
            repo.get("private", False)
        )

        if visibility == "private" and not privado:
            continue

        if visibility == "public" and privado:
            continue

        chave = nome.lower()

        if chave in vistos:
            continue

        vistos.add(chave)

        resultado.append(
            repo
        )

    return resultado


# ============================================================
# URL
# ============================================================

def url_clone(
    repo: dict
) -> str:

    return repo.get(
        "clone_url"
    ) or (
        "https://github.com/"
        + repo["full_name"]
        + ".git"
    )


def nome_local(
    repo: dict
) -> str:

    return repo[
        "name"
    ]


# ============================================================
# GIT ASKPASS
# ============================================================

def criar_git_askpass(
    token: str
) -> Path:

    diretorio = Path(
        tempfile.mkdtemp(
            prefix="github_askpass_"
        )
    )

    if os.name == "nt":

        arquivo = (
            diretorio /
            "askpass.cmd"
        )

        # O token fica apenas no arquivo
        # temporário durante o clone.
        conteudo = (
            "@echo off\n"
            f"echo {token}\n"
        )

    else:

        arquivo = (
            diretorio /
            "askpass.sh"
        )

        conteudo = (
            "#!/bin/sh\n"
            "printf '%s\\n' "
            + repr(token)
            + "\n"
        )

    arquivo.write_text(
        conteudo,
        encoding="utf-8"
    )

    if os.name != "nt":

        arquivo.chmod(
            stat.S_IRUSR |
            stat.S_IWUSR |
            stat.S_IXUSR
        )

    return arquivo


def remover_git_askpass(
    arquivo: Path | None
) -> None:

    if arquivo is None:
        return

    try:

        diretorio = (
            arquivo.parent
        )

        arquivo.unlink(
            missing_ok=True
        )

        diretorio.rmdir()

    except OSError:
        pass


# ============================================================
# GIT
# ============================================================

def executar_git(
    comando: list[str],
    cwd: Path | None = None,
    env: dict[str, str] | None = None
) -> bool:

    try:

        resultado = subprocess.run(
            comando,
            cwd=cwd,
            env=env,
            check=False
        )

        return (
            resultado.returncode == 0
        )

    except FileNotFoundError:

        print(
            color(
                "❌ Git não está instalado "
                "ou não está no PATH.",
                RED
            )
        )

        return False

    except KeyboardInterrupt:

        print(
            "\n⚠️ Operação cancelada."
        )

        return False


# ============================================================
# CLONE
# ============================================================

def clonar_repositorio(
    repo: dict,
    destino: Path,
    token: str | None,
    atualizar: bool
) -> bool:

    nome = nome_local(
        repo
    )

    full_name = repo[
        "full_name"
    ]

    url = url_clone(
        repo
    )

    pasta = destino / nome

    privado = bool(
        repo.get(
            "private",
            False
        )
    )

    tipo = "🔒 PRIVADO" if privado else "🌐 PÚBLICO"

    print()
    print("=" * 72)
    print(
        f"📦 {full_name}"
    )
    print(
        f"   {tipo}"
    )
    print(
        f"   📁 {pasta}"
    )
    print("=" * 72)

    # --------------------------------------------------------
    # JÁ EXISTE
    # --------------------------------------------------------

    if pasta.exists():

        if not (
            pasta / ".git"
        ).exists():

            print(
                color(
                    "⚠️ Pasta existe, "
                    "mas não é um repositório Git.",
                    YELLOW
                )
            )

            return False

        if not atualizar:

            print(
                "ℹ️ Já baixado."
            )

            return True

        print(
            "🔄 Atualizando..."
        )

        ambiente = os.environ.copy()

        askpass = None

        if token:

            askpass = (
                criar_git_askpass(
                    token
                )
            )

            ambiente[
                "GIT_ASKPASS"
            ] = str(
                askpass.resolve()
            )

            ambiente[
                "GIT_TERMINAL_PROMPT"
            ] = "0"

        try:

            return executar_git(
                [
                    "git",
                    "pull",
                    "--ff-only"
                ],
                cwd=pasta,
                env=ambiente
            )

        finally:

            remover_git_askpass(
                askpass
            )

    # --------------------------------------------------------
    # CLONE
    # --------------------------------------------------------

    destino.mkdir(
        parents=True,
        exist_ok=True
    )

    ambiente = os.environ.copy()

    askpass = None

    if token:

        askpass = (
            criar_git_askpass(
                token
            )
        )

        ambiente[
            "GIT_ASKPASS"
        ] = str(
            askpass.resolve()
        )

        ambiente[
            "GIT_TERMINAL_PROMPT"
        ] = "0"

    try:

        sucesso = executar_git(
            [
                "git",
                "clone",
                "--progress",
                url,
                str(pasta)
            ],
            env=ambiente
        )

    finally:

        remover_git_askpass(
            askpass
        )

    if sucesso:

        print(
            color(
                f"✅ {full_name} baixado.",
                GREEN
            )
        )

    else:

        print(
            color(
                f"❌ Falha: {full_name}",
                RED
            )
        )

        # Limpa clone incompleto.
        if pasta.exists():

            try:

                if not (
                    pasta / ".git"
                ).exists():

                    shutil.rmtree(
                        pasta
                    )

            except OSError:
                pass

    return sucesso


# ============================================================
# TOKEN
# ============================================================

def obter_token(
    prompt: bool
) -> str | None:

    token = os.environ.get(
        "MY_GITHUB_TOKEN"
    )

    if token:

        return token.strip()

    if prompt:

        print()
        print(
            "🔐 GitHub Personal Access Token"
        )

        print(
            "O token não será exibido."
        )

        token = getpass.getpass(
            "Token: "
        ).strip()

        if token:

            return token

    return None


# ============================================================
# EXIBIR LISTA
# ============================================================

def mostrar_repositorios(
    repositorios: list[dict]
) -> None:

    print()
    print("=" * 72)
    print(
        "📋 REPOSITÓRIOS ENCONTRADOS"
    )
    print("=" * 72)

    for indice, repo in enumerate(
        repositorios,
        start=1
    ):

        privado = repo.get(
            "private",
            False
        )

        tipo = (
            "🔒 PRIVADO"
            if privado
            else "🌐 PÚBLICO"
        )

        nome = repo.get(
            "full_name",
            "?"
        )

        arquivado = repo.get(
            "archived",
            False
        )

        sufixo = (
            " | 📦 ARQUIVADO"
            if arquivado
            else ""
        )

        print(
            f"{indice:4d}. "
            f"{tipo} "
            f"{nome}"
            f"{sufixo}"
        )

    print("=" * 72)


# ============================================================
# RESUMO
# ============================================================

def resumo(
    repositorios: list[dict]
) -> None:

    privados = sum(
        1
        for repo in repositorios
        if repo.get("private", False)
    )

    publicos = (
        len(repositorios)
        - privados
    )

    print()
    print(
        color(
            "📊 RESUMO DA DESCOBERTA",
            CYAN
        )
    )

    print(
        f"   Total:   {len(repositorios)}"
    )

    print(
        f"   Públicos: {publicos}"
    )

    print(
        f"   Privados: {privados}"
    )


# ============================================================
# MAIN
# ============================================================

def main() -> int:

    parser = argparse.ArgumentParser(
        description=(
            "Lista e baixa automaticamente "
            "repositórios do GitHub."
        )
    )

    # --------------------------------------------------------
    # ALVO
    # --------------------------------------------------------

    grupo = parser.add_mutually_exclusive_group(
        required=True
    )

    grupo.add_argument(
        "--mine",
        action="store_true",
        help=(
            "Lista todos os repositórios "
            "acessíveis pelo PAT."
        )
    )

    grupo.add_argument(
        "--user",
        help=(
            "Usuário do GitHub."
        )
    )

    grupo.add_argument(
        "--org",
        help=(
            "Organização do GitHub."
        )
    )

    # --------------------------------------------------------
    # VISIBILIDADE
    # --------------------------------------------------------

    parser.add_argument(
        "--visibility",
        choices=[
            "all",
            "public",
            "private"
        ],
        default="all",
        help=(
            "Filtra por visibilidade "
            "(padrão: all)."
        )
    )

    # --------------------------------------------------------
    # TOKEN
    # --------------------------------------------------------

    parser.add_argument(
        "--prompt-token",
        action="store_true",
        help=(
            "Solicita o PAT de forma segura."
        )
    )

    # --------------------------------------------------------
    # DESTINO
    # --------------------------------------------------------

    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=(
            "Pasta de destino "
            f"(padrão: {DEFAULT_OUTPUT})."
        )
    )

    # --------------------------------------------------------
    # ATUALIZAÇÃO
    # --------------------------------------------------------

    parser.add_argument(
        "--update",
        "-u",
        action="store_true",
        help=(
            "Atualiza repositórios "
            "já existentes."
        )
    )

    # --------------------------------------------------------
    # SOMENTE LISTAR
    # --------------------------------------------------------

    parser.add_argument(
        "--list-only",
        action="store_true",
        help=(
            "Lista os repositórios "
            "sem baixá-los."
        )
    )

    # --------------------------------------------------------
    # PULAR ARQUIVADOS
    # --------------------------------------------------------

    parser.add_argument(
        "--skip-archived",
        action="store_true",
        help=(
            "Não baixa repositórios arquivados."
        )
    )

    args = parser.parse_args()

    # ========================================================
    # TOKEN
    # ========================================================

    token = obter_token(
        args.prompt_token
    )

    # --mine necessita autenticação
    if args.mine and not token:

        print(
            color(
                "\n❌ --mine exige um "
                "Personal Access Token.",
                RED
            )
        )

        print()
        print(
            "Use:"
        )

        print(
            "  export MY_GITHUB_TOKEN="
            '"github_pat_..."'
        )

        print()

        print(
            "ou:"
        )

        print(
            "  --prompt-token"
        )

        return 1

    # ========================================================
    # CABEÇALHO
    # ========================================================

    print()
    print("=" * 72)
    print(
        "🐙 GITHUB BULK DOWNLOADER"
    )
    print("=" * 72)

    if token:

        print(
            "🔐 PAT: disponível"
        )

    else:

        print(
            "🌐 Modo: público"
        )

    print(
        f"📁 Destino: "
        f"{args.output.resolve()}"
    )

    # ========================================================
    # DESCOBERTA
    # ========================================================

    repositorios = []

    # --------------------------------------------------------
    # MEUS REPOSITÓRIOS
    # --------------------------------------------------------

    if args.mine:

        usuario = (
            obter_usuario_autenticado(
                token
            )
        )

        if not usuario:

            return 1

        print()
        print(
            f"👤 Usuário autenticado: "
            f"{usuario.get('login')}"
        )

        repositorios = (
            listar_repositorios_autenticados(
                token,
                args.visibility
            )
        )

    # --------------------------------------------------------
    # ORGANIZAÇÃO
    # --------------------------------------------------------

    elif args.org:

        repositorios = (
            listar_repositorios_organizacao(
                args.org,
                token,
                args.visibility
            )
        )

    # --------------------------------------------------------
    # USUÁRIO
    # --------------------------------------------------------

    elif args.user:

        repositorios = (
            listar_repositorios_usuario(
                args.user,
                token,
                args.visibility
            )
        )

    # ========================================================
    # FILTRAR
    # ========================================================

    repositorios = (
        normalizar_repositorios(
            repositorios,
            args.visibility
        )
    )

    # ========================================================
    # NENHUM
    # ========================================================

    if not repositorios:

        print()
        print(
            color(
                "⚠️ Nenhum repositório encontrado.",
                YELLOW
            )
        )

        print()
        print(
            "Verifique:"
        )

        print(
            "  • PAT válido"
        )

        print(
            "  • permissões do PAT"
        )

        print(
            "  • acesso à organização"
        )

        print(
            "  • nome do usuário/organização"
        )

        return 1

    # ========================================================
    # MOSTRAR
    # ========================================================

    mostrar_repositorios(
        repositorios
    )

    resumo(
        repositorios
    )

    # ========================================================
    # SOMENTE LISTAGEM
    # ========================================================

    if args.list_only:

        print()
        print(
            "ℹ️ --list-only ativo."
        )

        print(
            "Nenhum repositório será baixado."
        )

        return 0

    # ========================================================
    # ARQUIVADOS
    # ========================================================

    if args.skip_archived:

        antes = len(
            repositorios
        )

        repositorios = [
            repo
            for repo in repositorios
            if not repo.get(
                "archived",
                False
            )
        ]

        depois = len(
            repositorios
        )

        print()
        print(
            f"📦 Repositórios arquivados "
            f"ignorados: {antes - depois}"
        )

    # ========================================================
    # DESTINO
    # ========================================================

    args.output.mkdir(
        parents=True,
        exist_ok=True
    )

    # ========================================================
    # DOWNLOAD
    # ========================================================

    sucesso = 0
    falhas = 0
    existentes = 0

    print()
    print("=" * 72)
    print(
        "⬇️ INICIANDO DOWNLOAD"
    )
    print("=" * 72)

    for repo in repositorios:

        pasta = (
            args.output /
            nome_local(repo)
        )

        ja_existia = (
            pasta.exists()
            and
            (pasta / ".git").exists()
        )

        resultado = (
            clonar_repositorio(
                repo=repo,
                destino=args.output,
                token=token,
                atualizar=args.update
            )
        )

        if resultado:

            if ja_existia:
                existentes += 1
            else:
                sucesso += 1

        else:

            falhas += 1

    # ========================================================
    # RESULTADO FINAL
    # ========================================================

    print()
    print("=" * 72)
    print(
        "📊 RESULTADO FINAL"
    )
    print("=" * 72)

    print(
        f"📦 Repositórios processados: "
        f"{len(repositorios)}"
    )

    print(
        color(
            f"✅ Baixados: {sucesso}",
            GREEN
        )
    )

    print(
        f"🔄 Existentes/atualizados: "
        f"{existentes}"
    )

    print(
        color(
            f"❌ Falhas: {falhas}",
            RED if falhas else GREEN
        )
    )

    print(
        f"📁 Local: "
        f"{args.output.resolve()}"
    )

    print("=" * 72)

    return 2 if falhas else 0


# ============================================================
# EXECUÇÃO
# ============================================================

if __name__ == "__main__":

    sys.exit(
        main()
    )