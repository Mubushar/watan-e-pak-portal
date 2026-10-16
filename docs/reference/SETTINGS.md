# Runtime settings

Read with the MCP tool `portal_settings(action='get')` or `GET /portal/settings`; write with `portal_settings(action='update', updates={...})` or `PUT /portal/settings`.

| Group | Keys |
| --- | --- |
| `accounting` | `aging_buckets`, `currency`, `currency_symbol`, `default_cap_rate`, `default_commission_rate`, `default_discount_rate`, `default_hold_years`, `default_income_tax_rate`, `default_mortgage_rate`, `default_mortgage_years`, `default_rent_escalation`, `default_sales_tax_rate`, `depreciation_years_buildings`, `depreciation_years_equipment`, `fiscal_year_start_day`, `fiscal_year_start_month` |
| `advertising` | `currency`, `currency_symbol`, `default_slot`, `house_ad_body`, `house_ad_title`, `impression_weight_floor`, `max_per_slot`, `sponsored_label` |
| `agentic` | `approval_required_levels`, `autonomy_levels`, `default_autonomy`, `orchestration_max_agents`, `smart_action_sla_hours`, `summary_chars` |
| `assumptions` | `annual_property_tax_rate`, `annual_rental_yield`, `avg_household_size`, `commercial_activity_factor`, `construction_cost_per_sqft`, `default_dwelling_persons`, `economic_multiplier`, `infrastructure_cost_per_sqft`, `jobs_per_million_pkr_construction`, `land_development_cost_per_sqft`, `occupancy_rate`, `operational_jobs_per_1000_sqm`, `persons_per_bedroom` |
| `auth` | `channels`, `default_country_code`, `expose_otp`, `otp_length`, `otp_max_attempts`, `otp_max_per_hour`, `otp_purposes`, `otp_resend_cooldown_seconds`, `otp_ttl_seconds`, `password_min_length`, `pbkdf2_iterations`, `session_ttl_hours` |
| `commercial` | `billing_interval`, `currency`, `default_platform_share`, `default_unit_price`, `vat_rate` |
| `construction` | `city_multipliers`, `consultancy_pct`, `contingency_pct`, `currency`, `currency_symbol`, `default_building_type`, `default_city`, `default_quality_tier`, `default_system`, `escalation_cagr`, `floor_premium_from`, `floor_premium_pct`, `overhead_profit_pct`, `preliminaries_pct`, `quality_base_rate_sqft`, `quality_labels` |
| `content` | `default_language`, `site_name`, `supported_languages`, `tagline` |
| `factor_weights` | `demand`, `development`, `economic`, `infrastructure`, `political`, `regulatory`, `social` |
| `forecast` | `base_price_cagr`, `cost_inflation_cagr`, `default_build_years`, `growth_sensitivity`, `land_cost_share` |
| `intelligence` | `anomaly_z_threshold`, `buyer_weights` |
| `leasing` | `channels`, `default_rent_floor_margin`, `renewal_notice_days`, `response_sla_minutes`, `screening` |
| `maintenance` | `age_factor_cap`, `age_factor_pct_per_year`, `age_grace_years`, `city_multipliers`, `currency`, `currency_symbol`, `default_build_rate_sqft`, `default_city`, `default_property_type`, `default_tier`, `inflation_cagr` |
| `marketing` | `channel_quality`, `content_kinds`, `default_sla_hours`, `inactive_days`, `reengagement_min_score` |
| `messaging` | `attachment_link_ttl_minutes`, `attachment_max_mb`, `currency`, `deep_link_base`, `digest_hour`, `disclaimer`, `edit_window_minutes`, `email`, `message_max_length`, `quiet_hours`, `rate_limit_burst`, `rate_limit_per_minute`, `read_receipts_default`, `retention_days_default`, `search_min_chars`, `telegram`, `workspace` |
| `pmo` | `cost_overrun_amber_pct`, `cost_overrun_red_pct`, `cpi_amber`, `cpi_green`, `currency`, `currency_symbol`, `default_contingency_pct`, `default_priority`, `default_project_type`, `default_shift_hours`, `disclaimer`, `eac_method`, `net_working_days_per_month`, `overalloc_threshold_pct`, `quality_amber`, `quality_green`, `rest_weekday`, `risk_amber_score`, `risk_red_score`, `slip_amber_days`, `slip_red_days`, `spi_amber`, `spi_green`, `stale_progress_days`, `working_days_per_week` |
| `scenarios` | `base`, `optimistic`, `pessimistic`, `stress` |
| `tools` | `agent_commission_rate`, `currency`, `default_marla_sqft`, `disclaimer`, `vat_rate` |
| `transactions` | `default_commission_rate`, `default_splits`, `fall_through_probability`, `reminder_lead_days`, `vat_rate` |

## Current values

```json
{
  "assumptions": {
    "avg_household_size": 5.6,
    "persons_per_bedroom": 1.6,
    "default_dwelling_persons": 4.5,
    "occupancy_rate": 0.85,
    "construction_cost_per_sqft": {
      "house": 4500.0,
      "building": 5000.0,
      "apartment": 6000.0,
      "office": 7000.0,
      "shop": 6500.0,
      "floor": 5500.0,
      "space": 4000.0,
      "warehouse": 3500.0,
      "shed": 2500.0,
      "plot": 0.0
    },
    "infrastructure_cost_per_sqft": 350.0,
    "land_development_cost_per_sqft": 250.0,
    "jobs_per_million_pkr_construction": 12.0,
    "operational_jobs_per_1000_sqm": 1.8,
    "economic_multiplier": 1.8,
    "annual_property_tax_rate": 0.005,
    "annual_rental_yield": 0.04,
    "commercial_activity_factor": 3.0
  },
  "forecast": {
    "base_price_cagr": 0.075,
    "growth_sensitivity": 0.11,
    "cost_inflation_cagr": 0.08,
    "default_build_years": 3,
    "land_cost_share": 0.3
  },
  "factor_weights": {
    "development": 0.2,
    "infrastructure": 0.16,
    "economic": 0.2,
    "social": 0.12,
    "political": 0.14,
    "regulatory": 0.1,
    "demand": 0.08
  },
  "scenarios": {
    "optimistic": {
      "label": "Optimistic",
      "cagr_delta": 0.045,
      "cost_multiplier": 1.08,
      "probability": 0.25
    },
    "base": {
      "label": "Base",
      "cagr_delta": 0.0,
      "cost_multiplier": 1.0,
      "probability": 0.5
    },
    "pessimistic": {
      "label": "Pessimistic",
      "cagr_delta": -0.055,
      "cost_multiplier": 1.12,
      "probability": 0.2
    },
    "stress": {
      "label": "Stress",
      "cagr_delta": -0.14,
      "cost_multiplier": 1.2,
      "probability": 0.05
    }
  },
  "accounting": {
    "currency": "PKR",
    "currency_symbol": "Rs",
    "fiscal_year_start_month": 7,
    "fiscal_year_start_day": 1,
    "default_sales_tax_rate": 0.17,
    "default_income_tax_rate": 0.15,
    "default_commission_rate": 0.02,
    "default_rent_escalation": 0.1,
    "default_discount_rate": 0.12,
    "default_mortgage_rate": 0.21,
    "default_mortgage_years": 20,
    "default_hold_years": 5,
    "default_cap_rate": 0.07,
    "depreciation_years_buildings": 40,
    "depreciation_years_equipment": 8,
    "aging_buckets": [
      30,
      60,
      90
    ]
  },
  "auth": {
    "otp_length": 6,
    "otp_ttl_seconds": 300,
    "otp_max_attempts": 5,
    "otp_resend_cooldown_seconds": 30,
    "otp_max_per_hour": 10,
    "otp_purposes": [
      "signup",
      "login",
      "reset_password"
    ],
    "session_ttl_hours": 24,
    "password_min_length": 8,
    "pbkdf2_iterations": 120000,
    "expose_otp": true,
    "channels": [
      "sms",
      "email"
    ],
    "default_country_code": "+92"
  },
  "content": {
    "site_name": "Arz-e-Pak Real Estate Portal",
    "tagline": "Pakistan's smart, data-driven property marketplace",
    "default_language": "en",
    "supported_languages": [
      "en",
      "ur"
    ]
  },
  "advertising": {
    "currency": "PKR",
    "currency_symbol": "Rs",
    "sponsored_label": "Sponsored",
    "house_ad_title": "Advertise here",
    "house_ad_body": "Reach thousands of buyers, investors and developers across Pakistan.",
    "max_per_slot": 6,
    "default_slot": "infeed",
    "impression_weight_floor": 1.0
  },
  "construction": {
    "currency": "PKR",
    "currency_symbol": "Rs",
    "default_city": "Lahore",
    "default_building_type": "house",
    "default_quality_tier": "standard",
    "default_system": "rcc_frame",
    "escalation_cagr": 0.085,
    "preliminaries_pct": 4.0,
    "contingency_pct": 3.0,
    "consultancy_pct": 4.0,
    "overhead_profit_pct": 10.0,
    "floor_premium_pct": 1.5,
    "floor_premium_from": 2,
    "city_multipliers": {
      "Lahore": 1.0,
      "Karachi": 1.06,
      "Islamabad": 1.08,
      "Rawalpindi": 1.02,
      "Faisalabad": 0.97,
      "Multan": 0.95,
      "Peshawar": 0.98,
      "Quetta": 0.96,
      "Gujranwala": 0.97,
      "Hyderabad": 0.95
    },
    "quality_base_rate_sqft": {
      "economy": 3300.0,
      "standard": 4600.0,
      "premium": 6500.0,
      "luxury": 9500.0
    },
    "quality_labels": {
      "economy": "Economy",
      "standard": "Standard",
      "premium": "Premium",
      "luxury": "Luxury"
    }
  },
  "maintenance": {
    "currency": "PKR",
    "currency_symbol": "Rs",
    "default_property_type": "house",
    "default_tier": "standard",
    "default_city": "Lahore",
    "inflation_cagr": 0.07,
    "age_factor_pct_per_year": 2.0,
    "age_grace_years": 5,
    "age_factor_cap": 1.6,
    "default_build_rate_sqft": 4600.0,
    "city_multipliers": {
      "Lahore": 1.0,
      "Karachi": 1.06,
      "Islamabad": 1.08,
      "Rawalpindi": 1.02,
      "Faisalabad": 0.97,
      "Multan": 0.95,
      "Peshawar": 0.98,
      "Quetta": 0.96
    }
  },
  "agentic": {
    "default_autonomy": "assist",
    "autonomy_levels": [
      "suggest",
      "assist",
      "autonomous"
    ],
    "approval_required_levels": [
      "suggest",
      "assist"
    ],
    "summary_chars": 480,
    "smart_action_sla_hours": {
      "urgent": 4,
      "high": 24,
      "normal": 72
    },
    "orchestration_max_agents": 6
  },
  "transactions": {
    "default_commission_rate": 0.02,
    "vat_rate": 0.17,
    "default_splits": {
      "platform_share": 0.2,
      "listing_agent_share": 0.4,
      "selling_agent_share": 0.4
    },
    "fall_through_probability": 0.08,
    "reminder_lead_days": 3
  },
  "intelligence": {
    "buyer_weights": {
      "price_fit": 0.22,
      "commute": 0.2,
      "schools": 0.12,
      "safety": 0.1,
      "amenities": 0.12,
      "liquidity": 0.08,
      "condition": 0.08,
      "size_fit": 0.08
    },
    "anomaly_z_threshold": 1.0
  },
  "leasing": {
    "default_rent_floor_margin": 0.03,
    "channels": [
      "web_chat",
      "whatsapp",
      "sms",
      "email",
      "voice"
    ],
    "response_sla_minutes": 5,
    "renewal_notice_days": 90,
    "screening": {
      "min_income_to_rent": 3.0,
      "min_score": 60,
      "conditional_score": 48
    }
  },
  "marketing": {
    "inactive_days": 45,
    "reengagement_min_score": 35,
    "channel_quality": {
      "referral": 0.95,
      "walk_in": 0.9,
      "website": 0.7,
      "portal": 0.72,
      "call": 0.8,
      "whatsapp": 0.75,
      "sms": 0.6,
      "web_chat": 0.72,
      "voice": 0.78,
      "email": 0.65
    },
    "default_sla_hours": 4,
    "content_kinds": [
      "listing_description",
      "social_post",
      "reel_script",
      "email",
      "market_report",
      "video_script"
    ]
  },
  "commercial": {
    "currency": "USD",
    "vat_rate": 0.17,
    "default_unit_price": 0.05,
    "billing_interval": "monthly",
    "default_platform_share": 0.2
  },
  "tools": {
    "currency": "PKR",
    "vat_rate": 0.17,
    "agent_commission_rate": 0.02,
    "default_marla_sqft": 272.25,
    "disclaimer": "Indicative figures for planning and comparison. Statutory rates (stamp duty, CVT, registration, capital-gains tax) and Islamic-calendar dates change over time; confirm with the district/DC office and the official moon-sighting announcement before relying on them."
  },
  "pmo": {
    "currency": "PKR",
    "currency_symbol": "Rs",
    "working_days_per_week": 6,
    "rest_weekday": 6,
    "default_shift_hours": 8,
    "default_project_type": "construction",
    "default_priority": "medium",
    "net_working_days_per_month": 26.0,
    "spi_green": 0.95,
    "spi_amber": 0.9,
    "cpi_green": 0.95,
    "cpi_amber": 0.9,
    "slip_amber_days": 5,
    "slip_red_days": 15,
    "cost_overrun_amber_pct": 3.0,
    "cost_overrun_red_pct": 8.0,
    "quality_green": 85.0,
    "quality_amber": 70.0,
    "risk_amber_score": 10,
    "risk_red_score": 16,
    "stale_progress_days": 14,
    "overalloc_threshold_pct": 100.0,
    "default_contingency_pct": 5.0,
    "eac_method": "cpi",
    "disclaimer": "Planned/earned-value figures are indicative management information. Date arithmetic uses a six-day (Mon\u2013Sat) working week; align with the contract's own calendar before use in formal claims."
  },
  "messaging": {
    "workspace": "Arz-e-Pak",
    "currency": "PKR",
    "message_max_length": 4000,
    "edit_window_minutes": 15,
    "attachment_max_mb": 25,
    "attachment_link_ttl_minutes": 30,
    "retention_days_default": 1095,
    "rate_limit_per_minute": 60,
    "rate_limit_burst": 20,
    "quiet_hours": {
      "start": "21:00",
      "end": "08:00"
    },
    "digest_hour": 9,
    "search_min_chars": 2,
    "read_receipts_default": true,
    "deep_link_base": "/messaging/portal",
    "telegram": {
      "enabled": true,
      "max_text": 320,
      "attach_allowed": false,
      "bot_name": "ArzPakPortalBot",
      "link_code_ttl_minutes": 15,
      "urgent_priority": "high"
    },
    "email": {
      "from": "no-reply@arzepak.pk",
      "reply_to": "support@arzepak.pk",
      "digest": "instant",
      "subject_prefix": "[Arz-e-Pak]"
    },
    "disclaimer": "Notifications are queued and written to the outbox by the in-process dispatcher; a production deployment runs the same queue from a background worker and hands e-mail/Telegram payloads to a provider. Telegram and e-mail payloads never carry attachments or confidential document content - only short text and an authenticated deep link."
  }
}
```

