# paper-search-mcp-server

> Japanese version continues after English version. / 日本語版は英語版の後に続きます。

Single local stdio MCP server for academic paper search and Obsidian `@survey` workflows.

**Cursor on Ubuntu (canonical):** MCP display name is **`paperSearch`**. Cursor launches `python -m academic_mcp_server.survey.mcp` from this repo (survey tool profile). The Python package remains `academic_mcp_server`. Secrets stay in the shell (`ACADEMIC_MCP_SEMANTIC_SCHOLAR_API_KEY`), not in this repository.

The full connector surface is still available as `python -m academic_mcp_server.server`.

This repository provides one MCP server process, not three separate servers. The MCP entrypoint is intentionally thin, while API-specific behavior is split into dedicated connector modules and shared normalization helpers.

## Cursor / Ubuntu

User MCP (`~/.cursor/mcp.json`) is deployed by [wsl-rule](https://github.com/kota-may478/wsl-rule). Shape:

    "paperSearch": {
      "command": "~/.local/share/paper-search-mcp-server/.venv/bin/python",
      "args": ["-m", "academic_mcp_server.survey.mcp"],
      "cwd": "~/Insync/01_Private/Program/paper-search-mcp-server",
      "env": {
        "PYTHONPATH": "~/Insync/01_Private/Program/paper-search-mcp-server/src",
        "ACADEMIC_MCP_SEMANTIC_SCHOLAR_API_KEY": "${env:ACADEMIC_MCP_SEMANTIC_SCHOLAR_API_KEY}",
        "ACADEMIC_MCP_CONTACT_EMAIL": "you@example.org"
      }
    }

Put the Semantic Scholar key in `~/.bashrc` **before** the interactive-shell guard:

    ./scripts/configure-bashrc-env.sh --key YOUR_KEY --email you@example.org

Survey bootstrap (same package):

    python -m academic_mcp_server.survey.cli bootstrap --article-dir ... --survey-name ... ...

Check credentials (does not print secrets):

    python -m academic_mcp_server.survey.cli auth-status

## What It Does

- Exposes paper-search tools to GitHub Copilot in VS Code through MCP.
- Searches Semantic Scholar, arXiv, and Crossref from one server.
- Downloads and analyzes arXiv full text from source files or PDF, including figure and table captions when source files are available.
- Supports deeper literature workflows such as citations, references, author lookup, recommendations, and Crossref journal/funder/type slices.
- Normalizes paper metadata into a shared schema where practical.
- Uses VS Code MCP input variables so secrets are not committed to the repository.
- Sends logging to stderr only, which is safe for stdio MCP transport.

## Prerequisites

- Python 3.11 or newer
- A local virtual environment at `.venv`
- VS Code with GitHub Copilot and MCP support enabled

Semantic Scholar API access works without an API key at lower public limits, but an API key is strongly recommended because the public tier can return HTTP 429 quickly. Crossref requires a contact email for responsible API identification. OpenAlex polite-pool access uses a contact email as well, managed through environment variables or MCP inputs.

## Installation

From the workspace root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

On macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

## Configuration

This repository no longer tracks `.vscode/mcp.json`. You can run the server in either of these ways:

- User profile `mcp.json`: recommended when you want `paperSearch` available from any workspace.
- Workspace `.vscode/mcp.json`: recommended when you want the config to stay relative to the current clone while iterating on MCP settings.

Use one placement at a time for the `paperSearch` server ID unless you intentionally rename one of them.

### Option A: User Profile `mcp.json`

Merge the server into your VS Code user profile MCP config. On Windows, that file is typically `C:/Users/<you>/AppData/Roaming/Code/User/mcp.json`.

Use absolute paths so the server can start even when a different workspace is open:

```json
{
	"inputs": [
		{
			"type": "promptString",
			"id": "academic-paper-semantic-scholar-api-key",
			"description": "Semantic Scholar API key for paperSearch (required)",
			"password": true
		},
		{
			"type": "promptString",
			"id": "academic-paper-contact-email",
			"description": "Contact email for Crossref and paperSearch"
		},
		{
			"type": "promptString",
			"id": "academic-paper-openalex-contact-email",
			"description": "Optional dedicated contact email for OpenAlex polite pool"
		}
	],
	"servers": {
		"paperSearch": {
			"type": "stdio",
			"command": "C:/path/to/academic-mcp-server-copilot/.venv/Scripts/python.exe",
			"args": [
				"-m",
				"academic_mcp_server.server"
			],
			"cwd": "C:/path/to/academic-mcp-server-copilot",
			"env": {
				"PYTHONPATH": "C:/path/to/academic-mcp-server-copilot/src",
				"PYTHONUNBUFFERED": "1",
				"ACADEMIC_MCP_SEMANTIC_SCHOLAR_API_KEY": "${input:academic-paper-semantic-scholar-api-key}",
				"ACADEMIC_MCP_CONTACT_EMAIL": "${input:academic-paper-contact-email}",
				"ACADEMIC_MCP_OPENALEX_CONTACT_EMAIL": "${input:academic-paper-openalex-contact-email}"
			},
			"dev": {
				"watch": "C:/path/to/academic-mcp-server-copilot/src/**/*.py",
				"debug": true
			}
		}
	}
}
```

On macOS or Linux, replace the interpreter path with `.venv/bin/python` and adjust the absolute paths accordingly.

### Option B: Workspace `.vscode/mcp.json`

Create `.vscode/mcp.json` locally when you want the config to follow the current checkout through `${workspaceFolder}`:

```json
{
	"inputs": [
		{
			"type": "promptString",
			"id": "academic-paper-semantic-scholar-api-key",
			"description": "Semantic Scholar API key for paperSearch (required)",
			"password": true
		},
		{
			"type": "promptString",
			"id": "academic-paper-contact-email",
			"description": "Contact email for Crossref and paperSearch"
		},
		{
			"type": "promptString",
			"id": "academic-paper-openalex-contact-email",
			"description": "Optional dedicated contact email for OpenAlex polite pool"
		}
	],
	"servers": {
		"paperSearch": {
			"type": "stdio",
			"command": "${workspaceFolder}/.venv/Scripts/python.exe",
			"args": [
				"-m",
				"academic_mcp_server.server"
			],
			"env": {
				"PYTHONPATH": "${workspaceFolder}/src",
				"PYTHONUNBUFFERED": "1",
				"ACADEMIC_MCP_SEMANTIC_SCHOLAR_API_KEY": "${input:academic-paper-semantic-scholar-api-key}",
				"ACADEMIC_MCP_CONTACT_EMAIL": "${input:academic-paper-contact-email}",
				"ACADEMIC_MCP_OPENALEX_CONTACT_EMAIL": "${input:academic-paper-openalex-contact-email}"
			},
			"dev": {
				"watch": "${workspaceFolder}/src/**/*.py",
				"debug": true
			}
		}
	}
}
```

This repository ignores `.vscode/mcp.json`, so you can keep a workspace-local override without re-adding it to git.

Environment variables consumed by the server:

- `ACADEMIC_MCP_SEMANTIC_SCHOLAR_API_KEY` (required)
- `ACADEMIC_MCP_CONTACT_EMAIL`
- `ACADEMIC_MCP_REQUEST_TIMEOUT_SECONDS` (optional, default `20`)
- `ACADEMIC_MCP_ARXIV_EXPORT_QUERY_TIMEOUT_SECONDS` (optional, default `60`; used for `arxiv_search` Atom queries on `export.arxiv.org`; effective value is `max(REQUEST_TIMEOUT, this value)`)
- `ACADEMIC_MCP_CACHE_TTL_SECONDS` (optional, default `300`)
- `ACADEMIC_MCP_DEFAULT_LIMIT` (optional, default `10`)

## Available Tools

- `semantic_scholar_search`: search Semantic Scholar by keyword
- `semantic_scholar_paper`: fetch a single Semantic Scholar paper by identifier
- `semantic_scholar_paper_batch`: fetch multiple Semantic Scholar papers in one batch
- `semantic_scholar_citations`: fetch papers that cite a Semantic Scholar paper
- `semantic_scholar_references`: fetch papers referenced by a Semantic Scholar paper
- `semantic_scholar_author_search`: search Semantic Scholar authors by name
- `semantic_scholar_author`: fetch a single Semantic Scholar author by ID
- `semantic_scholar_author_papers`: fetch papers for a Semantic Scholar author
- `semantic_scholar_recommended_papers`: fetch recommended papers for a paper
- `semantic_scholar_recommend_from_examples`: fetch recommendations from positive and negative example papers
- `survey_paper_context`: build a survey-oriented paper context using Semantic Scholar for overview metadata, OpenAlex-first references/citations, and optional arXiv full-text enrichment
- `survey_query_contexts`: search, rank, and analyze multiple survey candidates in one batch while preserving evidence/disclosure metadata for each paper
- `arxiv_search`: search arXiv via the Atom API
- `arxiv_paper`: fetch a single arXiv paper by arXiv ID or URL
- `arxiv_full_text`: download and analyze arXiv full text from source files or PDF, with figure/table captions when available
- `crossref_search_works`: search Crossref works metadata
- `crossref_work_by_doi`: fetch a Crossref work by DOI
- `crossref_journal_works`: fetch Crossref works for a journal ISSN
- `crossref_funder_works`: fetch Crossref works for a funder ID
- `crossref_type_works`: fetch Crossref works for a Crossref work type
- `search_papers`: run a normalized cross-source search from one tool call

The normalized paper response includes fields such as source, source ID, title, authors, author details, abstract, publication and update dates, DOI, venue, publisher, URL, PDF URL, citation metrics, open-access hints, subjects, publication types, funders, and source-specific metadata when the upstream source provides them.

The `arxiv_full_text` response additionally returns extracted full text, the extraction method used (`source` or `pdf`), truncation metadata, and figure/table caption data when source parsing succeeds.

## Run In VS Code

### User Profile Workflow

1. Open this repository once and install the package into its `.venv` with `python -m pip install -e .`.
2. Open your user profile `mcp.json` and point `paperSearch` at this repository with absolute paths.
3. From any workspace, open the MCP UI or run `MCP: List Servers` and start `paperSearch`.
4. Enter the requested MCP input values when VS Code prompts for them.

### Workspace Workflow

1. Open this repository in VS Code.
2. Install the package into the workspace `.venv` with `python -m pip install -e .`.
3. Create `.vscode/mcp.json` locally from the workspace example above.
4. Start the server from the MCP UI or run `MCP: List Servers` and start `paperSearch`.
5. Enter the requested MCP input values when VS Code prompts for them.

If tool metadata does not refresh after edits, run `MCP: Reset Cached Tools` and restart the server.

## Security Notes

- Real secrets are not stored in tracked files.
- Both the user profile and workspace-local MCP setups use VS Code MCP input variables rather than hardcoded credentials.
- Local secret files such as `.env` are ignored by `.gitignore`.
- This server writes logs to stderr only so MCP protocol traffic on stdout remains clean.

## Notes On API Behavior

- Semantic Scholar sends `x-api-key` only when a key is configured, and this server serializes Semantic Scholar traffic to 1 request per second cumulatively across its Graph and Recommendations endpoints.
- When Semantic Scholar exhausts local retries on HTTP 429, survey-oriented tools now surface that relation traversal as `pending_rate_limited` work instead of failing the entire batch immediately. This allows downstream PRISMA-style prompts to distinguish `closure not reached yet` from `search completed`.
- Semantic Scholar paper and relation lookups cache canonical `paperId` mappings for DOI and other external IDs, so forward/backward snowballing after search results does not need to re-resolve the same paper repeatedly.
- Semantic Scholar paper and relation lookups also accept bare arXiv IDs, arXiv URLs, and versioned arXiv IDs such as `2311.02009v3`; these are normalized to versionless `arXiv:2311.02009` before lookup so snowballing tools can reuse them safely.
- Semantic Scholar exposes additional tools for paper batches, citations, references, authors, and recommendations.
- Relation traversal now prefers OpenAlex first when a DOI is available, because OpenAlex exposes both public `referenced_works` and public cited-by traversal with more stable anonymous access than Semantic Scholar's public tier.
- Survey-style single-paper analysis now uses Semantic Scholar as the primary source for title and abstract, keeps OpenAlex as the primary source for references and citations, and optionally enriches the result with arXiv full text when an arXiv record is found by explicit arXiv ID or normalized title match.
- Batch survey analysis can reduce MCP request count because search, candidate selection, and multiple paper-context lookups are performed inside one server call while reusing the same in-process caches. This reduces client orchestration overhead and can reduce duplicate identifier resolution, although it does not guarantee fewer upstream API calls for every query.
- Backward snowballing order is `OpenAlex -> Semantic Scholar -> Crossref`.
- Forward snowballing order is `OpenAlex -> Semantic Scholar`.
- Crossref remains the final backward-only fallback because public REST exposes deposited `reference` lists and `is-referenced-by-count`, but not the anonymous full citing-work list.
- For overview lookups, the fallback order is `Semantic Scholar -> OpenAlex -> Crossref`. When Semantic Scholar resolves the paper but lacks an abstract, OpenAlex or Crossref can be used only to fill the missing abstract while keeping the resolved paper source as Semantic Scholar.
- When neither abstract nor full text is publicly available, the server now emits a `title_only` content assessment with low confidence and an explicit article note stating that only the title and sparse metadata were checked. This is intended to be carried into downstream survey writing.
- OpenAlex requests always include a polite-pool contact email. The server uses `ACADEMIC_MCP_OPENALEX_CONTACT_EMAIL` when set, otherwise it reuses `ACADEMIC_MCP_CONTACT_EMAIL`.
- OpenAlex does not require an API key for this basic usage. An OpenAlex key is only needed later if you want materially higher-volume usage.
- arXiv uses the legacy query API and enforces single-request behavior with at least a 3-second interval between requests, matching the current arXiv API terms.
- arXiv exact lookup uses `id_list` so you can fetch a specific paper and keep richer arXiv metadata.
- arXiv full-text analysis prefers `/src/<id>` to parse TeX sources and extract figure/table captions, then falls back to `/pdf/<id>.pdf` text extraction when source files are unavailable or non-textual.
- Crossref always sends both `mailto` and `User-Agent` using the configured contact email.
- Crossref does not publish the same fixed RPS limit in the documentation referenced here, so this server uses the polite pool headers, caches responses, and backs off when Crossref responds with rate-limit or temporary-overload statuses.
- Crossref exposes deeper slices through journal, funder, and type endpoints in addition to general works search.
- Unified search returns partial results with per-source errors when one upstream service fails.

---

## Academic MCP Server 日本語

Semantic Scholar、arXiv、Crossref を 1 つのローカル stdio MCP サーバーから検索できるリポジトリです。

この実装は 3 つの別サーバーではなく、1 つの MCP サーバープロセスとして動作します。一方で内部実装は API ごとにコネクタを分離し、正規化や設定は共通モジュールにまとめています。

## できること

- VS Code の GitHub Copilot から MCP ツールとして論文検索を利用できます。
- Semantic Scholar、arXiv、Crossref を単一サーバーで扱えます。
- 引用・被引用、著者探索、推薦論文、Crossref の journal/funder/type 単位の取得にも対応します。
- 可能な範囲で論文メタデータを共通スキーマへ正規化します。
- VS Code MCP の入力変数を使うため、秘密情報をリポジトリへコミットしません。
- stdio MCP で問題にならないよう、ログは stdout ではなく stderr にのみ出力します。

## 前提条件

- Python 3.11 以上
- `.venv` という名前のローカル仮想環境
- GitHub Copilot と MCP が利用できる VS Code

Semantic Scholar は API キーなしでも使えますが、公開レート制限により HTTP 429 が出やすいため API キーの利用を強く推奨します。Crossref では責任ある識別のため連絡先メールアドレスが必要です。

## セットアップ

ワークスペース直下で実行してください。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

macOS / Linux の場合:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

## 設定

このリポジトリでは `.vscode/mcp.json` を追跡しない構成に変更しました。代わりに、次の 2 通りで運用できます。

- user profile の `mcp.json`: どのワークスペースからでも `paperSearch` を使いたい場合に向いています。
- workspace の `.vscode/mcp.json`: 現在の clone に対して相対パスで設定したい場合に向いています。

同じ `paperSearch` という server ID を使うなら、基本的にはどちらか片方だけを有効にしてください。

### 方法 A: User Profile `mcp.json`

VS Code の user profile 側の `mcp.json` にサーバー設定をマージします。Windows では通常 `C:/Users/<you>/AppData/Roaming/Code/User/mcp.json` です。

どのワークスペースでも起動できるよう、絶対パスを使います。

```json
{
	"inputs": [
		{
			"type": "promptString",
			"id": "academic-paper-semantic-scholar-api-key",
			"description": "Semantic Scholar API key for paperSearch (required)",
			"password": true
		},
		{
			"type": "promptString",
			"id": "academic-paper-contact-email",
			"description": "Contact email for Crossref and paperSearch"
		}
	],
	"servers": {
		"paperSearch": {
			"type": "stdio",
			"command": "C:/path/to/academic-mcp-server-copilot/.venv/Scripts/python.exe",
			"args": [
				"-m",
				"academic_mcp_server.server"
			],
			"cwd": "C:/path/to/academic-mcp-server-copilot",
			"env": {
				"PYTHONPATH": "C:/path/to/academic-mcp-server-copilot/src",
				"PYTHONUNBUFFERED": "1",
				"ACADEMIC_MCP_SEMANTIC_SCHOLAR_API_KEY": "${input:academic-paper-semantic-scholar-api-key}",
				"ACADEMIC_MCP_CONTACT_EMAIL": "${input:academic-paper-contact-email}"
			},
			"dev": {
				"watch": "C:/path/to/academic-mcp-server-copilot/src/**/*.py",
				"debug": true
			}
		}
	}
}
```

macOS / Linux では Python 実行ファイルのパスを `.venv/bin/python` に変更し、他の絶対パスも環境に合わせて読み替えてください。

### 方法 B: Workspace `.vscode/mcp.json`

現在の checkout に対して相対パスで管理したい場合は、ローカルで `.vscode/mcp.json` を作成してください。

```json
{
	"inputs": [
		{
			"type": "promptString",
			"id": "academic-paper-semantic-scholar-api-key",
			"description": "Semantic Scholar API key for paperSearch (required)",
			"password": true
		},
		{
			"type": "promptString",
			"id": "academic-paper-contact-email",
			"description": "Contact email for Crossref and paperSearch"
		}
	],
	"servers": {
		"paperSearch": {
			"type": "stdio",
			"command": "${workspaceFolder}/.venv/Scripts/python.exe",
			"args": [
				"-m",
				"academic_mcp_server.server"
			],
			"env": {
				"PYTHONPATH": "${workspaceFolder}/src",
				"PYTHONUNBUFFERED": "1",
				"ACADEMIC_MCP_SEMANTIC_SCHOLAR_API_KEY": "${input:academic-paper-semantic-scholar-api-key}",
				"ACADEMIC_MCP_CONTACT_EMAIL": "${input:academic-paper-contact-email}"
			},
			"dev": {
				"watch": "${workspaceFolder}/src/**/*.py",
				"debug": true
			}
		}
	}
}
```

このリポジトリでは `.vscode/mcp.json` を `.gitignore` に入れているため、workspace ローカル設定を使っても再び追跡対象に戻りません。

サーバーが利用する環境変数:

- `ACADEMIC_MCP_SEMANTIC_SCHOLAR_API_KEY`（必須）
- `ACADEMIC_MCP_CONTACT_EMAIL`
- `ACADEMIC_MCP_REQUEST_TIMEOUT_SECONDS`（任意、既定値 `20`）
- `ACADEMIC_MCP_ARXIV_EXPORT_QUERY_TIMEOUT_SECONDS`（任意、既定値 `60`。`arxiv_search` が使う `export.arxiv.org` のクエリ専用。実効値は `max(REQUEST_TIMEOUT, 本変数)`）
- `ACADEMIC_MCP_CACHE_TTL_SECONDS`（任意、既定値 `300`）
- `ACADEMIC_MCP_DEFAULT_LIMIT`（任意、既定値 `10`）

## 利用できるツール

- `semantic_scholar_search`: Semantic Scholar のキーワード検索
- `semantic_scholar_paper`: Semantic Scholar の単一論文取得
- `semantic_scholar_paper_batch`: Semantic Scholar の複数論文一括取得
- `semantic_scholar_citations`: 指定論文を引用している論文の取得
- `semantic_scholar_references`: 指定論文が参照している論文の取得
- `semantic_scholar_author_search`: Semantic Scholar の著者検索
- `semantic_scholar_author`: Semantic Scholar の著者 ID による単一著者取得
- `semantic_scholar_author_papers`: 指定著者の論文一覧取得
- `semantic_scholar_recommended_papers`: 単一論文に対する推薦論文取得
- `semantic_scholar_recommend_from_examples`: 正例・負例に基づく推薦論文取得
- `arxiv_search`: arXiv Atom API による検索
- `arxiv_paper`: arXiv ID または URL による単一論文取得
- `crossref_search_works`: Crossref works 検索
- `crossref_work_by_doi`: DOI から Crossref の単一 work を取得
- `crossref_journal_works`: ISSN を指定した journal works 取得
- `crossref_funder_works`: funder ID を指定した works 取得
- `crossref_type_works`: work type を指定した works 取得
- `search_papers`: 複数ソースを横断した正規化済み検索

返却データには、source、source ID、title、authors、author details、abstract、publication/update date、DOI、venue、publisher、URL、PDF URL、引用指標、open access 関連情報、subjects、publication types、funders、source-specific metadata など、各 API が提供する範囲の共通項目が含まれます。

## VS Code での使い方

### User Profile 運用

1. このリポジトリを一度開き、`.venv` に `python -m pip install -e .` を実行します。
2. user profile 側の `mcp.json` に、このリポジトリへの絶対パスを使った `paperSearch` を設定します。
3. 任意のワークスペースから MCP UI か `MCP: List Servers` を開き、`paperSearch` を起動します。
4. VS Code に求められた入力値を登録します。

### Workspace 運用

1. このリポジトリを VS Code で開きます。
2. `.venv` に対して `python -m pip install -e .` を実行します。
3. 上の workspace 用サンプルをもとに、ローカルで `.vscode/mcp.json` を作成します。
4. MCP UI から起動するか、`MCP: List Servers` で `paperSearch` を起動します。
5. VS Code に求められた入力値を登録します。

ツール一覧が更新されない場合は、`MCP: Reset Cached Tools` を実行してからサーバーを再起動してください。

## セキュリティに関する注意

- 実際の秘密情報は追跡対象ファイルに保存しません。
- user profile 配置でも workspace 配置でも、ハードコードではなく VS Code MCP 入力変数を使います。
- `.env` などのローカル秘密情報ファイルは `.gitignore` で除外しています。
- stdout は MCP プロトコル用に空け、ログは stderr のみに出力します。

## API ごとの挙動

- Semantic Scholar は API キーが設定されている場合のみ `x-api-key` を送信し、このサーバーでは Graph / Recommendations をまとめて累積 1 request per second になるよう直列化しています。
- Semantic Scholar では一括取得、引用・被引用、著者、推薦論文の各 API も利用できます。
- Semantic Scholar の references が空でも DOI と reference count が残っている論文では、`semantic_scholar_references` が Crossref references に fallback して backward snowballing を継続します。
- arXiv は legacy query API を使い、利用規約に合わせて単一接続かつ 3 秒以上の間隔を強制します。
- arXiv の単一論文取得では `id_list` を使い、より正確に論文を取得します。
- arXiv の全文解析では `/src/<id>` を優先して TeX source を解析し、図表 caption を抽出します。source が扱えない投稿では `/pdf/<id>.pdf` のテキスト抽出へ自動で fallback します。
- Crossref には設定した連絡先メールアドレスを使って `mailto` と `User-Agent` を常に付与します。
- Crossref には同じ形の固定 RPS 制限は明記されていないため、polite pool 用の識別情報を付け、キャッシュし、rate limit や一時過負荷の応答に対して backoff します。
- Crossref では general works に加えて journal、funder、type ごとの works 取得も利用できます。
- 横断検索では一部ソースが失敗しても、成功したソースの結果を返しつつエラー内容を含めます。
