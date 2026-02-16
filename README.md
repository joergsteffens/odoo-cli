# odoo-cli

A Python command-line tool for calling Odoo's External JSON-2 API methods (Odoo 19+).

## 🎯 Overview

`odoo-cli` is a command-line tool for calling Odoo model methods exposed via the JSON-2 API.
It provides a fast and scriptable way to invoke server-side logic without writing custom integration code.

The included Python client can be reused independently of the CLI,
enabling seamless integration into scripts, services, and automation workflows.


## Motivation

Many Odoo tasks are still performed interactively in the UI, which makes them harder to reproduce, automate, and test. This project provides a small, scriptable interface to execute model methods remotely, so recurring operations can be run in a controlled and repeatable way from the command line or from Python code.

Besides being directly useful as a CLI tool, the project also serves as a minimal, working reference implementation of an Odoo JSON-2 client. Developers can reuse the included Python class or use the code as a starting point for their own integrations and automation tools.

It was also used during development and testing of the Thunderbird add-on:
https://addons.thunderbird.net/thunderbird/addon/odoo-email-importer/


## ✨ Features

- 🔌 **Call model methods** - Invoke Odoo model methods exposed via the JSON-2 API
- 🚀 **JSON-2 API Support** - Native support for Odoo's JSON-2 API (introduced in Odoo 19)
- 📦 **Lightweight** - Minimal dependencies
- 🔧 **Extensible** - Easy to add custom method wrappers
- 🔧 **Subcommands** - Includes useful subcommands such as importing an email into Odoo or exporting configuration to a directory.

## 📋 Requirements

- Python 3.6+
- optional: https://pypi.org/project/ConfigArgParse/
- Odoo 19 or higher (for JSON-2 API)
- Valid Odoo API key

## 🚀 Installation

```bash
git clone https://github.com/joergsteffens/odoo-cli.git

# Optional: Add to PATH
sudo ln -s $(pwd)/bin/odoo-cli /usr/local/bin/odoo-cli
```

## ⚡ Quickstart

```bash
odoo-cli --url https://your-instance.odoo.com --apikey your_api_key call res.partner search_read --args limit=3
```

## ⚙️ Configuration

Create a configuration file with your Odoo instance details:

```ini
[default]
url = https://your-instance.odoo.com
apikey = your_api_key_here
database = your_database_name (optional)
```

Database is normally not required.
It is only required, if you are running multiple databases on the same Odoo host.

If `ConfigArgParse` is available, this configuration can be provided on a ini config file by `--config <configfile.cfg>`.
Otherwise `--url`, `--apikey` and optionally `--database` must be provided as command line parameter.

### Getting an API Key

1. Log into your Odoo instance
2. Go to **Settings** → **Users & Companies** → **Users**
3. Select your user
4. Navigate to the **API Keys** tab
5. Click **New API Key** and save it securely

## 📖 Usage

### Generic API Method Calls

The core functionality is calling any `@api` method:

```bash
# Generic syntax
odoo-cli call <model> <method> [--json '{"key": "value"}'] [--args key1=value2 key2=value2 ...]

# Call search_read (most common)
odoo-cli call res.partner search_read --json '{
  "domain": [["is_company", "=", true]],
  "fields": ["name", "email"],
  "limit": 10
}'

# Call create
odoo-cli call res.partner create --json '{
  "vals_list": [
    {
        "name": "New Company 1",
        "email": "info@example1.com"
    },
    {
        "name": "New Company 2",
        "email": "info@example2.com"
    }    
  ]
}'

# Call write (update)
odoo-cli call res.partner write --json '{
  "ids": [123],
  "vals": {"phone": "+49 123 456789"}
}'
```

### Common Methods

While the tool can call any `@api` method, these are commonly used:

#### search_read
```bash
odoo-cli call res.partner search_read --json '{
  "fields": ["name", "email", "phone"],
  "limit": 5
}'
```

#### search
```bash
odoo-cli call res.partner search --json '{
  "domain": [["customer_rank", ">", 0]]
}'
```

#### read
```bash
odoo-cli call res.partner read --json '{
  "ids": [1, 2, 3],
  "fields": ["name", "email"]
}'
```

#### create
```bash
odoo-cli call res.partner create --json '{
  "vals_list": [
    {
        "name": "New Company 1",
        "email": "info@example1.com"
    }
  ]
}'
```

#### write
```bash
odoo-cli call res.partner write --json '{ "ids": [123], "vals": {"phone": "+49 123 456789"} }'
```

#### unlink
```bash
odoo-cli call res.partner unlink --json '{
  "ids": [123]
}'
```

### Custom Environment Methods

⚠️ **Note**: Custom methods in this repository may not work in your Odoo instance.
They are provided as examples for implementing your own custom workflows.

### Useful Extensions/Subcommands

- **list**                List objects of a resource.
- **show**                Show a single odoo object.
- **dump**                Dump a resource.
- **create**              Create a new odoo object.
- **mail-add**            Import an email (as file) into odoo.
- **config-dump**         Dump (parts of) the odoo configuration/data.

## 🔌 How It Works

The tool uses Odoo's External JSON-2 API endpoints:

```
POST /json/2/<model>/<method>
```

**Request format:**
```json
{
    "param1": "value1",
    "param2": "value2"
}
```

(depending on access rights and method exposure)

**Authentication:**

Authentication is done via the API-Key in an additional header:
```
"Authorization": "bearer <your_api_key_here>",
```

Any method decorated with `@api.model` or similar decorators in Odoo can be called through this endpoint.

## 📝 Python Library Usage

You can also use the underlying client as a Python library:

```python
from odoo_api import OdooApi

client = OdooApi(
    url="https://your-instance.odoo.com",
    api_key="your_api_key",
    database="your_database",
)

# Call any method
result = client.call(
    "res.partner",
    "search_read",
    domain=[["is_company", "=", True]],
    fields=["name", "email"],
    limit=10,
)
```

## 🛠️ Extending the Tool

## 📚 Understanding Odoo API Methods

### Universal Methods (work everywhere)

These methods are part of Odoo's ORM and available on all models:
- `search`, `search_read`, `search_count`
- `read`, `create`, `write`, `unlink`
- `fields_get`, `name_search`

### Model-Specific Methods

Many models have their own `@api` methods.

Check your model's Python code or 
https://your-instance.odoo.com/doc/ (or https://demo.odoo.com/doc)
to see available methods.

## 📄 License

This project is licensed under the GNU Affero General Public License v3.0 (AGPL-3.0) - see the [LICENSE](LICENSE) file for details.

## 🔗 Resources

- [Odoo 19 External JSON-2 API Documentation](https://www.odoo.com/documentation/19.0/developer/reference/external_api.html)
- [Odoo ORM Documentation](https://www.odoo.com/documentation/19.0/developer/reference/backend/orm.html)

## 🤝 Contributing

Contributions are welcome!

## ⚠️ Disclaimer

This is an unofficial tool and is not affiliated with or endorsed by Odoo S.A.

**Environment-Specific Methods**: Some methods included in this repository are specific to our Odoo environment and serve as examples. They may not work in your installation.
