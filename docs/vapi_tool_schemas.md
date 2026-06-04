# Vapi Dashboard Tool Schemas

Manual reference for configuring the HVAC Intelligence voice assistant in the [Vapi dashboard](https://dashboard.vapi.ai). Add each tool under **Assistant → Tools → Function**.

Existing tools (already configured): `get_customer_info`, `get_equipment_info`, `schedule_dispatch`, `query_churn_score`, `rag_knowledge_query`, `create_support_ticket`.

---

## create_customer

Create a new customer account when the caller is not in the CRM or wants a new account.

```json
{
  "type": "function",
  "function": {
    "name": "create_customer",
    "description": "Create a new HVAC customer account in the CRM. Use when the caller is new, not found by phone lookup, or explicitly asks to open a new account. Collect full name, service address, and confirm the caller ID phone number before calling.",
    "parameters": {
      "type": "object",
      "properties": {
        "full_name": {
          "type": "string",
          "description": "Customer's full legal name."
        },
        "phone_primary": {
          "type": "string",
          "description": "Primary phone in E.164 format, e.g. +19493313190."
        },
        "service_address_line1": {
          "type": "string",
          "description": "Street address line 1 for service location."
        },
        "service_address_city": {
          "type": "string",
          "description": "City for service location."
        },
        "service_address_state": {
          "type": "string",
          "description": "Two-letter US state code, e.g. CA."
        },
        "service_address_zip": {
          "type": "string",
          "description": "ZIP or postal code."
        },
        "email": {
          "type": "string",
          "description": "Optional email address."
        },
        "contract_type": {
          "type": "string",
          "enum": ["RESIDENTIAL_OTC", "ANNUAL_MAINTENANCE", "COMMERCIAL_SLA"],
          "description": "Contract type. Default RESIDENTIAL_OTC for most homeowners."
        },
        "notes": {
          "type": "string",
          "description": "Optional free-text notes about the customer."
        }
      },
      "required": [
        "full_name",
        "phone_primary",
        "service_address_line1",
        "service_address_city",
        "service_address_state",
        "service_address_zip"
      ]
    }
  }
}
```

---

## update_customer

Update an existing customer's contact or address details mid-call.

```json
{
  "type": "function",
  "function": {
    "name": "update_customer",
    "description": "Update an existing customer record. Use when the caller corrects their name, phone, email, service address, or asks to add notes. Requires customer_id from get_customer_info or call context.",
    "parameters": {
      "type": "object",
      "properties": {
        "customer_id": {
          "type": "string",
          "description": "UUID of the customer to update."
        },
        "full_name": {
          "type": "string",
          "description": "Updated full name."
        },
        "phone_primary": {
          "type": "string",
          "description": "Updated primary phone in E.164 format."
        },
        "email": {
          "type": "string",
          "description": "Updated email address."
        },
        "service_address_line1": {
          "type": "string",
          "description": "Updated street address line 1."
        },
        "service_address_line2": {
          "type": "string",
          "description": "Updated street address line 2."
        },
        "service_address_city": {
          "type": "string",
          "description": "Updated city."
        },
        "service_address_state": {
          "type": "string",
          "description": "Updated two-letter state code."
        },
        "service_address_zip": {
          "type": "string",
          "description": "Updated ZIP code."
        },
        "notes": {
          "type": "string",
          "description": "Notes to append or replace on the account."
        }
      },
      "required": ["customer_id"]
    }
  }
}
```

---

## create_equipment

Register HVAC equipment on a customer's account.

```json
{
  "type": "function",
  "function": {
    "name": "create_equipment",
    "description": "Register equipment (AC, furnace, heat pump, etc.) for a customer. Use after account creation or when a caller reports a unit not yet on file. Requires customer_id.",
    "parameters": {
      "type": "object",
      "properties": {
        "customer_id": {
          "type": "string",
          "description": "UUID of the customer who owns the equipment."
        },
        "equipment_type": {
          "type": "string",
          "enum": [
            "AC_UNIT",
            "FURNACE",
            "HEAT_PUMP",
            "WATER_HEATER",
            "ELECTRICAL_PANEL",
            "PLUMBING_SYSTEM",
            "INTERNET_ROUTER",
            "OTHER"
          ],
          "description": "Type of equipment being registered."
        },
        "make": {
          "type": "string",
          "description": "Manufacturer or brand, e.g. Carrier, Trane."
        },
        "model": {
          "type": "string",
          "description": "Model number or name."
        },
        "install_year": {
          "type": "integer",
          "description": "Year the unit was installed."
        },
        "serial_number": {
          "type": "string",
          "description": "Equipment serial number if known."
        },
        "known_issues": {
          "type": "array",
          "items": { "type": "string" },
          "description": "List of known recurring issues with this unit."
        }
      },
      "required": ["customer_id", "equipment_type"]
    }
  }
}
```

---

## update_dispatch

Correct or cancel a dispatch booking created during the call.

```json
{
  "type": "function",
  "function": {
    "name": "update_dispatch",
    "description": "Update or cancel a scheduled dispatch job. Use when the caller corrects the service address, changes their preferred appointment window, adds notes, or cancels a booking. Requires job_id from schedule_dispatch.",
    "parameters": {
      "type": "object",
      "properties": {
        "job_id": {
          "type": "string",
          "description": "UUID of the dispatch job to update."
        },
        "service_address_override": {
          "type": "string",
          "description": "Corrected service address as free text, e.g. '165 Deeley, Irvine CA'."
        },
        "preferred_window": {
          "type": "string",
          "description": "New preferred appointment window, e.g. 'tomorrow afternoon'."
        },
        "notes": {
          "type": "string",
          "description": "Additional notes or corrections to attach to the booking."
        },
        "cancel": {
          "type": "boolean",
          "description": "Set true to cancel the booking."
        }
      },
      "required": ["job_id"]
    }
  }
}
```

---

## lookup_service_info

Look up exact service pricing, duration, and descriptions from the tenant service catalog.

```json
{
  "type": "function",
  "function": {
    "name": "lookup_service_info",
    "description": "Look up HVAC service pricing, duration, and descriptions from the service catalog. Use for exact price questions (e.g. 'how much does AC diagnostic cost?'). For nuanced policy or 'what's included' questions, use rag_knowledge_query with namespace pricing instead.",
    "parameters": {
      "type": "object",
      "properties": {
        "query": {
          "type": "string",
          "description": "Natural language search, e.g. 'how much does AC repair cost'."
        },
        "category": {
          "type": "string",
          "description": "Filter by category: diagnostic, repair, maintenance, installation, emergency, or inspection."
        },
        "service_code": {
          "type": "string",
          "description": "Exact machine-readable service code, e.g. AC_DIAGNOSTIC."
        }
      }
    }
  }
}
```

---

## check_availability

Check real technician availability before confirming a booking. Call this before schedule_dispatch when the caller asks about appointment times.

```json
{
  "type": "function",
  "function": {
    "name": "check_availability",
    "description": "Find open appointment slots for HVAC service visits. Use when the caller asks about availability, timing, or 'when can someone come out'. Always call this before schedule_dispatch to offer specific slots.",
    "parameters": {
      "type": "object",
      "properties": {
        "preferred_date": {
          "type": "string",
          "description": "Natural language date preference: 'tomorrow', 'Monday', 'next week', or ISO date YYYY-MM-DD. Omit to start from tomorrow."
        },
        "duration_minutes": {
          "type": "integer",
          "description": "Expected job duration in minutes. Default 60."
        },
        "preferred_technician_id": {
          "type": "string",
          "description": "Optional UUID to check a specific technician only."
        },
        "num_days_to_check": {
          "type": "integer",
          "description": "How many days ahead to search (1-7). Default 3."
        }
      }
    }
  }
}
```

---

## Identity confirmation (system prompt — no tool)

On **call-start**, the backend injects identity confirmation instructions when a phone match is found. No dashboard change required — ensure the assistant system prompt allows following injected context from `assistantOverrides.model.systemPrompt`.

For **unknown callers**, the injected prompt guides onboarding via `create_customer` → optional `create_equipment` → `schedule_dispatch`.
