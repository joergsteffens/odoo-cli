# odoo-cli

A Python command-line tool for calling Odoo's External JSON-2 API methods (Odoo 19+).

## 🎯 Overview

`odoo-cli` is a flexible tool that allows you to call `@api.model` decorated method in Odoo 19+ through the External JSON-2 API.

## ✨ Features

- 🔌 **Call API Method** - Invoke any `@api.model` decorated method on Odoo models
- 🚀 **JSON-2 API Support** - Native support for Odoo's new External JSON-2 API
- 📦 **Lightweight** - Minimal dependencies
- 🔧 **Extensible** - Easy to add custom method wrappers

## 📋 Requirements

- Python 3.6+
- Odoo 19 or higher with External JSON-2 API enabled
- Valid Odoo API key

## 🚀 Installation

```bash
git clone https://github.com/joergsteffens/odoo-cli.git

# Optional: Add to PATH
sudo ln -s $(pwd)/bin/odoo-cli /usr/local/bin/odoo-cli
```

## ⚙️ Configuration

Create a configuration file with your Odoo instance details:

```ini
[default]
url = https://your-instance.odoo.com
api_key = your_api_key_here
database = your_database_name (optional)
```

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
odoo-cli call <model> <method> [--json '{"key": "value"}']

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

⚠️ **Note**: Custom methods in this repository may not work in your Odoo instance. They are provided as examples for implementing your own custom workflows.

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

**Authentication:**
```
Api-Key: your_api_key_here
```

Any method decorated with `@api.model` or similar decorators in Odoo can be called through this endpoint.

## 📝 Python Library Usage

You can also use the underlying client as a Python library:

```python
from odoo_api import OdooApi

client = OdooApi(
    url='https://your-instance.odoo.com',
    api_key='your_api_key',
    database='your_database'
)

# Call any method
result = client.call('res.partner', 'search_read', domain= [['is_company', '=', True]], fields = ['name', 'email'], 'limit' = 10)
})
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
