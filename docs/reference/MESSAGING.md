# Messaging catalogs

Generated from `messaging.py`. The end-to-end flows live in [`../MESSAGING_GUIDE.md`](../MESSAGING_GUIDE.md).

## Conversation kinds & states

* **Kinds** — `direct`, `group`, `channel`, `property`
* **Statuses** — `active`, `archived`, `locked`
* **Member roles** — `owner`, `admin`, `member`, `guest`
* **Presence** — `online`, `away`, `busy`, `offline`
* **Message types** — `text`, `system`, `attachment`, `action`, `property_link`
* **Action kinds** — `task`, `approval`, `verification`, `request`
* **Action statuses** — `open`, `in_progress`, `done`, `cancelled`
* **Notification states** — `queued`, `sent`, `read`, `failed`, `deferred`
* **Outbox channels** — `in_app`, `email`, `telegram`
* **Moderation actions** — `dismiss`, `delete_message`, `mute_author`, `escalate`
* **Report reasons** — `spam`, `abuse`, `confidential_leak`, `off_topic`, `other`

## Default channels

| Key | Name | Restricted | Roles allowed | Purpose |
| --- | --- | --- | --- | --- |
| `sales` | Sales | no | — | Listings, enquiries and deal coordination |
| `property_verification` | Property Verification | no | — | Title, document and site verification |
| `gis_mapping` | GIS & Mapping | no | — | Maps, georeferencing and spatial analysis |
| `customer_support` | Customer Support | no | — | Client queries and after-sales follow-up |
| `management` | Management | yes | owner, super_admin, admin, manager, management, director, principal | Approvals, finance and policy |
| `announcements` | Announcements | no | — | Company-wide notices |

Staff whose role is in `ADMIN_ROLES` (`owner`, `super_admin`, `admin`, `manager`, `management`, `director`, `principal`) may read any non-restricted channel without joining.

## Notification categories

| Category | Label | Default channels | Urgent |
| --- | --- | --- | --- |
| `mention` | Mentions | in_app, email, telegram | yes |
| `direct` | Direct messages | in_app, email, telegram | yes |
| `channel` | Channel messages | in_app | no |
| `property` | Property discussions | in_app, email | no |
| `lead` | New leads | in_app, email, telegram | yes |
| `approval` | Approvals | in_app, email, telegram | yes |
| `task` | Task updates | in_app, email | no |
| `system` | System notices | in_app | no |

## Attachment rules

Sensitive kinds are gated on the signed expiring link (owner/admin only for `restricted`, members for the rest). Attachments are always *references* — bytes never travel in a message.

| Kind | Extensions | Sensitive by default |
| --- | --- | --- |
| `pdf` | pdf | yes |
| `image` | jpg, jpeg, png, webp, gif | no |
| `cad` | dwg, dxf, dgn | yes |
| `spreadsheet` | xls, xlsx, csv, ods | yes |
| `document` | doc, docx, txt, md, rtf | no |
| `map` | geojson, kml, kmz, shp, tif, tiff | yes |
| `video` | mp4, mov, webm | no |
| `archive` | zip, rar, 7z, tar, gz | yes |
| `other` | — | no |

## Runtime limits

| Setting | Value |
| --- | --- |
| `message_max_length` | 4000 |
| `edit_window_minutes` | 15 |
| `attachment_max_mb` | 25 |
| `attachment_link_ttl_minutes` | 30 |
| `retention_days_default` | 1095 |
| `rate_limit_per_minute` | 60 |
| `rate_limit_burst` | 20 |
| `search_min_chars` | 2 |
| `quiet_hours` | 21:00–08:00 |
| `telegram.max_text` | 320 |
| `telegram.link_code_ttl_minutes` | 15 |
| `email.from` | no-reply@watanepak.pk |

