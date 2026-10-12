"""
SAAS SENDBID — Générateur de documentation Word
Crée le fichier SENDBID_StorageService_Documentation.docx
"""
from docx import Document
from docx.shared import Pt, RGBColor, Cm, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import datetime


# ── Couleurs WIB / SENDBID
C_DARK_BLUE  = RGBColor(0x1A, 0x1D, 0x27)
C_PURPLE     = RGBColor(0x6C, 0x63, 0xFF)
C_TEAL       = RGBColor(0x4E, 0xCD, 0xC4)
C_GREEN      = RGBColor(0x2E, 0xCC, 0x71)
C_RED        = RGBColor(0xE7, 0x4C, 0x3C)
C_ORANGE     = RGBColor(0xF3, 0x9C, 0x12)
C_LIGHT_GREY = RGBColor(0xF4, 0xF6, 0xF9)
C_MID_GREY   = RGBColor(0x94, 0xA3, 0xB8)
C_WHITE      = RGBColor(0xFF, 0xFF, 0xFF)
C_BLACK      = RGBColor(0x0F, 0x11, 0x17)
C_HEADER_BG  = RGBColor(0x24, 0x28, 0x38)


def set_cell_bg(cell, hex_color):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), hex_color.upper())
    tcPr.append(shd)


def set_cell_borders(cell, top='single', bottom='single', left='single', right='single', sz=4, color='DDDDDD'):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcBorders = OxmlElement('w:tcBorders')
    for edge, val in [('top', top), ('bottom', bottom), ('left', left), ('right', right)]:
        el = OxmlElement(f'w:{edge}')
        el.set(qn('w:val'), val)
        el.set(qn('w:sz'), str(sz))
        el.set(qn('w:color'), color)
        tcBorders.append(el)
    tcPr.append(tcBorders)


def add_horizontal_line(doc, color='6C63FF'):
    p = doc.add_paragraph()
    pPr = p._p.get_or_add_pPr()
    pBdr = OxmlElement('w:pBdr')
    bottom = OxmlElement('w:bottom')
    bottom.set(qn('w:val'), 'single')
    bottom.set(qn('w:sz'), '6')
    bottom.set(qn('w:color'), color)
    pBdr.append(bottom)
    pPr.append(pBdr)
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(2)
    return p


def style_heading(paragraph, level=1):
    """Apply custom heading style."""
    run = paragraph.runs[0] if paragraph.runs else paragraph.add_run(paragraph.text)
    if level == 1:
        run.font.size = Pt(20)
        run.font.color.rgb = C_PURPLE
        run.font.bold = True
    elif level == 2:
        run.font.size = Pt(15)
        run.font.color.rgb = C_DARK_BLUE
        run.font.bold = True
    elif level == 3:
        run.font.size = Pt(12)
        run.font.color.rgb = RGBColor(0x2C, 0x3E, 0x50)
        run.font.bold = True
    paragraph.paragraph_format.space_before = Pt(14)
    paragraph.paragraph_format.space_after = Pt(4)


def add_code_block(doc, code, caption=None):
    """Add a styled code/monospace block."""
    if caption:
        p = doc.add_paragraph()
        run = p.add_run(caption)
        run.font.size = Pt(8.5)
        run.font.color.rgb = C_MID_GREY
        run.font.italic = True
        p.paragraph_format.space_after = Pt(1)

    p = doc.add_paragraph()
    run = p.add_run(code)
    run.font.name = 'Courier New'
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(0x2D, 0x2D, 0x2D)
    p.paragraph_format.left_indent = Cm(0.8)
    p.paragraph_format.right_indent = Cm(0.8)
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(4)

    # Light grey background via shading the paragraph border
    pPr = p._p.get_or_add_pPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), 'F0F2F5')
    pPr.append(shd)
    return p


def add_info_box(doc, text, color_hex='6C63FF', label=None):
    """Add a colored info/warning box."""
    p = doc.add_paragraph()
    if label:
        run = p.add_run(f"{label}  ")
        run.font.bold = True
        run.font.size = Pt(10)
    run = p.add_run(text)
    run.font.size = Pt(10)
    p.paragraph_format.left_indent = Cm(0.6)
    p.paragraph_format.right_indent = Cm(0.6)
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(6)

    pPr = p._p.get_or_add_pPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    fill = {
        '6C63FF': 'EEF0FF',
        'E74C3C': 'FDECEA',
        '2ECC71': 'EAFAF1',
        'F39C12': 'FEF9E7',
    }.get(color_hex, 'F4F6F9')
    shd.set(qn('w:fill'), fill)
    pPr.append(shd)

    pBdr = OxmlElement('w:pBdr')
    left = OxmlElement('w:left')
    left.set(qn('w:val'), 'single')
    left.set(qn('w:sz'), '24')
    left.set(qn('w:color'), color_hex)
    pBdr.append(left)
    pPr.append(pBdr)
    return p


def add_styled_table(doc, headers, rows, col_widths=None):
    """Add a styled table with header row."""
    n_cols = len(headers)
    table = doc.add_table(rows=1 + len(rows), cols=n_cols)
    table.style = 'Table Grid'
    table.alignment = WD_TABLE_ALIGNMENT.LEFT

    # Header row
    hdr_row = table.rows[0]
    for i, h in enumerate(headers):
        cell = hdr_row.cells[i]
        set_cell_bg(cell, '242838')
        p = cell.paragraphs[0]
        p.clear()
        run = p.add_run(h)
        run.font.bold = True
        run.font.size = Pt(9.5)
        run.font.color.rgb = C_WHITE
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

    # Data rows
    for ri, row in enumerate(rows):
        bg = 'FFFFFF' if ri % 2 == 0 else 'F8F9FB'
        tr = table.rows[ri + 1]
        for ci, cell_val in enumerate(row):
            cell = tr.cells[ci]
            set_cell_bg(cell, bg)
            p = cell.paragraphs[0]
            p.clear()
            run = p.add_run(str(cell_val))
            run.font.size = Pt(9)
            run.font.color.rgb = RGBColor(0x2C, 0x3E, 0x50)

    # Column widths
    if col_widths:
        for ri in range(len(table.rows)):
            for ci, w in enumerate(col_widths):
                table.rows[ri].cells[ci].width = Cm(w)

    return table


# ═══════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════
def build_document():
    doc = Document()

    # Page margins
    for section in doc.sections:
        section.top_margin = Cm(2.2)
        section.bottom_margin = Cm(2.2)
        section.left_margin = Cm(2.5)
        section.right_margin = Cm(2.5)

    # Default font
    doc.styles['Normal'].font.name = 'Calibri'
    doc.styles['Normal'].font.size = Pt(10.5)

    # ── COVER PAGE ──────────────────────────────────────────────
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(60)
    p.paragraph_format.space_after = Pt(4)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run('SAAS SENDBID')
    run.font.size = Pt(36)
    run.font.bold = True
    run.font.color.rgb = C_PURPLE

    p2 = doc.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run2 = p2.add_run('Storage Service — Documentation Technique')
    run2.font.size = Pt(18)
    run2.font.color.rgb = RGBColor(0x2C, 0x3E, 0x50)

    add_horizontal_line(doc)

    p3 = doc.add_paragraph()
    p3.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run3 = p3.add_run('WIB Company  ·  Microservice de stockage local sécurisé\nSendBID / PayBID — Application mobile de transactions financières internationales')
    run3.font.size = Pt(11)
    run3.font.color.rgb = C_MID_GREY

    p4 = doc.add_paragraph()
    p4.paragraph_format.space_before = Pt(30)
    p4.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run4 = p4.add_run(f'Version 1.0  ·  {datetime.date.today().strftime("%d %B %Y")}')
    run4.font.size = Pt(10)
    run4.font.color.rgb = C_MID_GREY

    doc.add_page_break()

    # ── TABLE DES MATIÈRES ──────────────────────────────────────
    h = doc.add_heading('Table des matières', level=1)
    style_heading(h, 1)
    add_horizontal_line(doc)

    toc_items = [
        ('1.',  'Contexte et objectifs du projet', 3),
        ('2.',  'Architecture globale', 4),
        ('3.',  'Arborescence du projet', 5),
        ('4.',  'Arborescence des fichiers stockés sur disque', 7),
        ('5.',  'Modèle de données (PostgreSQL)', 8),
        ('6.',  'API REST — Endpoints', 9),
        ('7.',  'Sécurité', 12),
        ('8.',  'Authentification service-à-service', 13),
        ('9.',  'Gestion des fichiers sensibles vs publics', 14),
        ('10.', 'Configuration Nginx', 15),
        ('11.', 'Scripts de sauvegarde et monitoring', 16),
        ('12.', 'Script de migration depuis Emergent Storage', 17),
        ('13.', 'Intégration Django (remplacement Emergent SDK)', 18),
        ('14.', 'Interface utilisateur de test', 19),
        ('15.', 'Suite de tests automatisés (pytest)', 20),
        ('16.', 'Docker & déploiement', 21),
        ('17.', 'Checklist de mise en production', 22),
        ('18.', 'Variables d\'environnement', 23),
        ('19.', 'Adaptation pour l\'intégration — Contrat d\'API', 24),
        ('20.', 'Suite de tests d\'intégration — 107 cas', 26),
        ('21.', 'Guide d\'intégration — Fonctionnement de l\'API', 28),
        ('22.', 'Intégration React Native (application mobile)', 30),
        ('23.', 'Intégration Web — JavaScript / React / Vue', 34),
    ]

    for num, title, _ in toc_items:
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Cm(0.3)
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(2)
        run_num = p.add_run(f'{num}  ')
        run_num.font.bold = True
        run_num.font.color.rgb = C_PURPLE
        run_num.font.size = Pt(10.5)
        run_title = p.add_run(title)
        run_title.font.size = Pt(10.5)
        run_title.font.color.rgb = RGBColor(0x2C, 0x3E, 0x50)

    doc.add_page_break()

    # ════════════════════════════════════════════════════════════
    # 1. CONTEXTE ET OBJECTIFS
    # ════════════════════════════════════════════════════════════
    h = doc.add_heading('1. Contexte et objectifs du projet', level=1)
    style_heading(h, 1)
    add_horizontal_line(doc)

    doc.add_paragraph(
        'SendBID et PayBID sont des applications mobiles de transactions financières internationales '
        'développées par WIB Company. Le stack technique est composé de React Native pour le front-end mobile, '
        'Django REST Framework pour le backend API, et PostgreSQL comme base de données principale.'
    )

    h2 = doc.add_heading('Problématique initiale', level=2)
    style_heading(h2, 2)
    doc.add_paragraph(
        'Jusqu\'à présent, les fichiers uploadés par les utilisateurs (avatars, photos de carte d\'identité CNI, '
        'reçus de transactions) étaient envoyés à un service externe payant — Emergent Object Storage. '
        'Ce service représente un coût récurrent et introduit une dépendance externe pour des données sensibles.'
    )

    h2 = doc.add_heading('Objectif du projet', level=2)
    style_heading(h2, 2)
    doc.add_paragraph(
        'Construire un microservice "storage-service" déployé sur le propre VPS de WIB Company, qui :'
    )
    for item in [
        'Reçoit, valide, stocke et sert les fichiers uploadés par les utilisateurs',
        'Applique une séparation stricte entre fichiers publics (avatars) et fichiers sensibles (CNI, reçus)',
        'Garantit qu\'aucun fichier sensible ne soit jamais accessible via une URL publique',
        'Fournit des URLs signées à durée limitée pour l\'accès contrôlé aux fichiers sensibles',
        'Maintient un journal d\'audit de chaque accès à un document sensible',
        'Sauvegarde automatiquement les données avec rétention et chiffrement',
        'Permet une migration sans coupure depuis Emergent Storage',
        'S\'intègre avec le backend Django existant via un client HTTP sécurisé',
    ]:
        p = doc.add_paragraph(item, style='List Bullet')
        p.runs[0].font.size = Pt(10.5)

    add_info_box(doc,
        'Un fichier CNI (Carte Nationale d\'Identité) accessible par URL publique constitue une faille grave '
        'de protection des données personnelles (RGPD) et expose WIB Company à des sanctions légales. '
        'Ce projet traite ce risque comme priorité absolue.',
        color_hex='E74C3C', label='⚠  CRITIQUE :')

    doc.add_page_break()

    # ════════════════════════════════════════════════════════════
    # 2. ARCHITECTURE
    # ════════════════════════════════════════════════════════════
    h = doc.add_heading('2. Architecture globale', level=1)
    style_heading(h, 1)
    add_horizontal_line(doc)

    h2 = doc.add_heading('Schéma des flux', level=2)
    style_heading(h2, 2)

    add_code_block(doc, """\
┌──────────────────────────────────────────────────────────────────┐
│                      SAAS SENDBID                                │
│                React Native Mobile App                           │
└─────────────────────────┬────────────────────────────────────────┘
                          │ HTTPS
┌─────────────────────────▼────────────────────────────────────────┐
│                  Django REST Framework                           │
│              (Backend API — sendbird.com)                        │
│  Authentifie l'utilisateur, extrait user_id + role              │
│  Transmet l'identité au storage-service via headers             │
└────────┬──────────────────────────────────────────┬─────────────┘
         │ HTTPS + API Key + HMAC Signature          │
         │ X-User-Id, X-User-Role                    │
┌────────▼──────────────────────────────┐    ┌──────▼─────────────┐
│     SENDBID Storage Service           │    │   PostgreSQL        │
│         FastAPI  :8080                │    │  sendbid_storage    │
│                                       │    │  ┌───────────────┐  │
│  POST  /v1/files         (upload)     │◄──►│  │ stored_files  │  │
│  GET   /v1/files/{id}    (stream)     │    │  │ audit_logs    │  │
│  GET   /v1/files/{id}/signed          │    │  └───────────────┘  │
│  DELETE /v1/files/{id}                │    └────────────────────┘
│  GET   /v1/public/avatars/{id}        │
│  GET   /health                        │
└──────────────────┬────────────────────┘
                   │
       ┌───────────┴────────────────┐
       │                            │
┌──────▼──────────┐      ┌──────────▼─────────────────┐
│  /uploads/      │      │  Nginx (reverse proxy)     │
│  avatars/  ─────┼─────►│  /v1/public/avatars/ → CDN │
│  kyc/      ─────┼──    │  Cloudflare (avatars seul) │
│  receipts/ ─────┼──    │  BLOQUE kyc/ et receipts/  │
└─────────────────┘      └────────────────────────────┘""",
    caption='Figure 1 — Flux complet du Storage Service')

    h2 = doc.add_heading('Stack technique', level=2)
    style_heading(h2, 2)

    add_styled_table(doc,
        headers=['Composant', 'Technologie', 'Version', 'Rôle'],
        rows=[
            ['Backend API',     'FastAPI (Python)',        '0.109+',    'Endpoints REST, validation, streaming'],
            ['SGBD principal',  'PostgreSQL',              '16',        'Métadonnées fichiers, audit logs'],
            ['SGBD dev/test',   'SQLite (aiosqlite)',      '—',         'Développement local, tests'],
            ['ORM',             'SQLAlchemy (async)',      '2.0+',      'Modèles, requêtes async'],
            ['Serveur ASGI',    'Uvicorn',                 '0.27+',     'Serveur ASGI haute performance'],
            ['Traitement image','Pillow',                  '10.2+',     'Strip EXIF, ré-encodage images'],
            ['Proxy HTTP',      'Nginx',                   '1.24+',     'Reverse proxy + CDN avatars'],
            ['CDN',             'Cloudflare (gratuit)',    '—',         'Cache CDN avatars uniquement'],
            ['Containerisation','Docker + Compose',        '—',         'Déploiement reproductible'],
            ['Sauvegarde',      'Restic',                  '0.16+',     'Backup chiffré avec rétention'],
        ],
        col_widths=[3.5, 4.0, 2.5, 5.5]
    )

    doc.add_page_break()

    # ════════════════════════════════════════════════════════════
    # 3. ARBORESCENCE DU PROJET
    # ════════════════════════════════════════════════════════════
    h = doc.add_heading('3. Arborescence du projet', level=1)
    style_heading(h, 1)
    add_horizontal_line(doc)

    add_code_block(doc, """\
sendbid-storage-service/
│
├── app/                              ← Application FastAPI principale
│   ├── __init__.py
│   ├── main.py                       ← Point d'entrée, CORS, lifespan, routing
│   ├── config.py                     ← Settings Pydantic (env vars)
│   ├── database.py                   ← Engine SQLAlchemy async, session, init_db()
│   ├── models.py                     ← ORM : StoredFile, AuditLog, FileCategory
│   ├── schemas.py                    ← Schémas Pydantic (request/response)
│   ├── auth.py                       ← Middleware auth : API Key + HMAC
│   │
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── files.py                  ← POST/GET/DELETE /v1/files + signed URLs
│   │   ├── health.py                 ← GET /health + /v1/metrics
│   │   └── public.py                 ← GET /v1/public/avatars/{id} (sans auth)
│   │
│   └── utils/
│       ├── __init__.py
│       ├── file_validation.py        ← Magic bytes, MIME whitelist, anti-traversal
│       ├── image_processing.py       ← Strip EXIF/GPS, ré-encodage Pillow
│       ├── storage.py                ← Persistance disque, checksums SHA-256, signed URLs
│       └── audit.py                  ← Journal d'accès persisté en base
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                   ← Fixtures pytest-asyncio, fichiers JPEG/PNG/PDF test
│   ├── test_upload.py                ← 10 tests : valide, exécutable, vide, MIME faux...
│   ├── test_access_control.py        ← 12 tests : owner, autre user, admin, signed URL
│   └── test_security.py              ← 9 tests CRITIQUES : KYC jamais public, cache...
│
├── nginx/
│   └── storage-service.conf          ← Config Nginx (public/privé + Cloudflare CDN)
│
├── scripts/
│   ├── backup.sh                     ← Restic backup avec rétention 7j + 4sem + 3mois
│   ├── monitor_disk.sh               ← Alerte disque > 80% (email + Slack)
│   └── migrate_from_emergent.py      ← Migration depuis Emergent Storage avec checksum
│
├── django_integration/
│   ├── __init__.py
│   └── storage_client.py             ← Client HTTP Django (remplace SDK Emergent)
│
├── ui/
│   └── index.html                    ← Interface de test complète (SPA dark mode)
│
├── uploads/                          ← Répertoire de stockage (créé au démarrage)
│   ├── avatars/                      ← Fichiers publics (avatars)
│   ├── kyc/                          ← CNI — JAMAIS public
│   └── receipts/                     ← Reçus — JAMAIS public
│
├── .env                              ← Variables d'env (local dev — SQLite)
├── .env.example                      ← Exemple de config (production)
├── docker-compose.yml                ← PostgreSQL + service containerisé
├── Dockerfile                        ← Image Docker production
├── requirements.txt                  ← Dépendances Python
└── sendbid_storage.db                ← SQLite (dev uniquement)""",
    caption='Arborescence complète du projet')

    doc.add_page_break()

    # ════════════════════════════════════════════════════════════
    # 4. ARBORESCENCE DES FICHIERS SUR DISQUE
    # ════════════════════════════════════════════════════════════
    h = doc.add_heading('4. Arborescence des fichiers stockés sur disque', level=1)
    style_heading(h, 1)
    add_horizontal_line(doc)

    doc.add_paragraph(
        'Les fichiers sont organisés en sous-dossiers par année/mois pour éviter les répertoires plats '
        'contenant des millions d\'entrées, ce qui dégrade les performances du système de fichiers.'
    )

    add_code_block(doc, """\
/var/app/uploads/                    ← Racine (permission 750, user sendbid)
│
├── avatars/                         ← PUBLICS — servis par Nginx + Cloudflare CDN
│   ├── 2025/
│   │   ├── 01/
│   │   │   ├── a3f8b2c1d4e5f6a7b8c9d0e1f2a3b4c5   ← UUID sans extension
│   │   │   └── ...
│   │   └── 02/
│   └── 2026/
│       └── 10/
│           └── ...
│
├── kyc/                             ← SENSIBLES — aucun accès Nginx public
│   ├── 2025/
│   │   └── 12/
│   │       └── b4c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1
│   └── 2026/
│       └── 10/
│           └── ...
│
└── receipts/                        ← SENSIBLES — aucun accès Nginx public
    ├── 2025/
    │   └── 11/
    │       └── c5d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2
    └── 2026/
        └── 10/
            └── ...""",
    caption='Organisation des fichiers sur le VPS')

    add_info_box(doc,
        'Les noms de fichiers sont des UUID v4 générés côté serveur (ex: a3f8b2c1d4e5f6a7...). '
        'Le nom original du client est ignoré pour éliminer tout risque de path traversal ou d\'injection.',
        color_hex='6C63FF', label='ℹ  Sécurité :')

    h2 = doc.add_heading('Permissions Linux recommandées (production)', level=2)
    style_heading(h2, 2)

    add_code_block(doc, """\
# Créer l'utilisateur dédié
sudo useradd -r -s /sbin/nologin sendbid

# Permissions strictes
sudo chown -R sendbid:sendbid /var/app/uploads
sudo chmod 750 /var/app/uploads
sudo chmod 750 /var/app/uploads/avatars
sudo chmod 750 /var/app/uploads/kyc        # Lecture seule par l'app
sudo chmod 750 /var/app/uploads/receipts

# Pas de listing de répertoire (Nginx)
# autoindex off;  ← dans nginx.conf""",
    caption='Commandes Linux — permissions fichiers')

    doc.add_page_break()

    # ════════════════════════════════════════════════════════════
    # 5. MODÈLE DE DONNÉES
    # ════════════════════════════════════════════════════════════
    h = doc.add_heading('5. Modèle de données (PostgreSQL)', level=1)
    style_heading(h, 1)
    add_horizontal_line(doc)

    h2 = doc.add_heading('Table : stored_files', level=2)
    style_heading(h2, 2)

    add_styled_table(doc,
        headers=['Colonne', 'Type', 'Nullable', 'Description'],
        rows=[
            ['id',              'VARCHAR(36)', 'NON', 'UUID v4 généré côté serveur — jamais le nom client'],
            ['owner_user_id',   'VARCHAR(255)','NON', 'ID de l\'utilisateur propriétaire du fichier'],
            ['category',        'VARCHAR(50)', 'NON', 'avatars | kyc | receipts — indexé'],
            ['original_filename','VARCHAR(512)','OUI', 'Nom original du client (information seulement)'],
            ['stored_path',     'VARCHAR(1024)','NON', 'Chemin relatif sur disque : avatars/2026/10/uuid'],
            ['mime_type',       'VARCHAR(128)', 'NON', 'Type MIME détecté par magic bytes (pas l\'extension)'],
            ['size_bytes',      'INTEGER',     'NON', 'Taille réelle du fichier après traitement'],
            ['checksum_sha256', 'VARCHAR(64)', 'NON', 'Hash SHA-256 du contenu — pour vérification intégrité'],
            ['is_deleted',      'BOOLEAN',     'NON', 'Suppression logique (purge planifiée)'],
            ['created_at',      'DATETIME',   'NON', 'Horodatage création (UTC)'],
            ['deleted_at',      'DATETIME',   'OUI', 'Horodatage suppression logique'],
        ],
        col_widths=[4.0, 3.0, 2.2, 7.3]
    )

    h2 = doc.add_heading('Table : audit_logs', level=2)
    style_heading(h2, 2)

    add_styled_table(doc,
        headers=['Colonne', 'Type', 'Description'],
        rows=[
            ['id',                'INTEGER (PK)', 'Identifiant auto-incrémenté'],
            ['file_id',           'VARCHAR(36)',  'FK → stored_files.id — fichier concerné'],
            ['requester_user_id', 'VARCHAR(255)', 'Qui a effectué l\'action'],
            ['requester_role',    'VARCHAR(50)',  'Rôle : user | admin | kyc_agent | signed_url'],
            ['action',            'VARCHAR(50)',  'upload | download | download_signed | delete'],
            ['ip_address',        'VARCHAR(64)',  'Adresse IP du demandeur'],
            ['user_agent',        'VARCHAR(512)', 'User-Agent HTTP'],
            ['timestamp',         'DATETIME',    'Horodatage précis de l\'accès'],
            ['success',           'BOOLEAN',     'Succès ou échec de l\'opération'],
            ['details',           'TEXT',        'Informations complémentaires (ex: expires=...)'],
        ],
        col_widths=[4.5, 3.5, 8.5]
    )

    doc.add_page_break()

    # ════════════════════════════════════════════════════════════
    # 6. API REST
    # ════════════════════════════════════════════════════════════
    h = doc.add_heading('6. API REST — Endpoints', level=1)
    style_heading(h, 1)
    add_horizontal_line(doc)

    add_info_box(doc,
        'Tous les endpoints /v1/ requièrent le header X-API-Key. '
        'En production, les headers X-Timestamp et X-Signature (HMAC-SHA256) sont également obligatoires. '
        'L\'identité de l\'utilisateur final est transmise via X-User-Id et X-User-Role.',
        color_hex='6C63FF', label='🔐  Auth :')

    endpoints = [
        # (méthode, chemin, auth, description, exemple_request, exemple_response)
        (
            'POST', '/v1/files', 'Requise',
            'Upload d\'un fichier. Validation stricte (magic bytes, taille, MIME whitelist, anti-exécutable). '
            'Strip EXIF pour les images. Nom de fichier généré côté serveur.',
            'multipart/form-data:\n  file: <binaire>\n  category: "avatars" | "kyc" | "receipts"\n  owner_user_id: "user-001"',
            '201 Created\n{\n  "file_id": "a3f8b2c1-...",\n  "category": "avatars",\n  "size": 45231,\n  "mime": "image/jpeg",\n  "checksum": "abc123...",\n  "url": "http://cdn.../v1/public/avatars/a3f8b2c1-..."\n}'
        ),
        (
            'GET', '/v1/files', 'Requise',
            'Liste les fichiers de l\'utilisateur courant. Un admin voit tous les fichiers. '
            'Paramètre optionnel : ?category=kyc',
            'Headers: X-API-Key, X-User-Id, X-User-Role\nQuery: ?category=kyc (optionnel)',
            '200 OK\n[{"file_id": "...", "category": "kyc", "mime_type": "application/pdf", ...}]'
        ),
        (
            'GET', '/v1/files/{file_id}', 'Requise',
            'Stream le fichier en réponse. Vérifie que le demandeur est le propriétaire ou admin/kyc_agent. '
            'Journalise l\'accès pour les fichiers sensibles. Headers de cache adaptés (public vs privé).',
            'Headers: X-API-Key, X-User-Id, X-User-Role',
            '200 OK — binaire streamed\nContent-Type: image/jpeg\nCache-Control: no-store (sensible)'
        ),
        (
            'GET', '/v1/files/{file_id}/meta', 'Requise',
            'Retourne les métadonnées d\'un fichier sans streamer le contenu binaire.',
            'Headers: X-API-Key, X-User-Id',
            '200 OK\n{"file_id": "...", "category": "kyc", "size_bytes": 85432, "checksum_sha256": "...", ...}'
        ),
        (
            'GET', '/v1/files/{file_id}/signed', 'Requise',
            'Génère une URL signée HMAC à durée limitée (par défaut 60s) pour accéder à un fichier sensible '
            'sans exposer les credentials. Paramètre optionnel : ?ttl=300',
            'Headers: X-API-Key, X-User-Id\nQuery: ?ttl=60',
            '200 OK\n{"file_id": "...", "signed_url": "http://.../download?expires=...&sig=...", "expires_at": "...", "ttl_seconds": 60}'
        ),
        (
            'GET', '/v1/files/{file_id}/download', 'Aucune (URL signée)',
            'Download via URL signée. Valide la signature HMAC et l\'expiration. '
            'Ne requiert pas de header d\'authentification — utilisable directement dans un navigateur.',
            'Query: ?expires=1728000000&sig=abc123...',
            '200 OK — binaire streamed\n  ou\n403 Forbidden si signature invalide ou expirée'
        ),
        (
            'DELETE', '/v1/files/{file_id}', 'Requise',
            'Suppression logique (is_deleted=True). Le fichier physique est conservé pour purge planifiée. '
            'Seul le propriétaire ou un admin peut supprimer.',
            'Headers: X-API-Key, X-User-Id',
            '200 OK\n{"file_id": "...", "message": "File marked for deletion"}'
        ),
        (
            'GET', '/v1/public/avatars/{file_id}', 'Aucune',
            'Sert un avatar public sans authentification. En production, Nginx sert directement depuis disque. '
            'IMPORTANT : uniquement les avatars — aucune route publique pour kyc/ ou receipts/.',
            'Aucun header requis',
            '200 OK — binaire image\nCache-Control: public, max-age=31536000, immutable'
        ),
        (
            'GET', '/health', 'Aucune',
            'Readiness probe complet : statut DB + usage disque par catégorie + checks détaillés '
            '(dir_avatars, dir_kyc, dir_receipts). Retourne "degraded" si DB down ou disque > 80%.',
            '—',
            '200 OK\n{"status":"ok","version":"1.0.0","env":"production","uptime_seconds":3642.1,\n "db":"ok","disk_usage":{...},"categories":{...},"checks":{"database":{"status":"ok"},...}}'
        ),
        (
            'GET', '/v1/ping', 'Aucune',
            'Liveness probe ultra-léger — aucune vérification DB ni disque. '
            'Utilisé par les load-balancers, orchestrateurs (k8s) et health-checkers.',
            '—',
            '200 OK\n{"pong": true, "version": "1.0.0", "service": "sendbid-storage"}'
        ),
        (
            'GET', '/v1/info', 'Aucune',
            'Retourne le contrat d\'API complet : catégories acceptées, limites de taille, '
            'types MIME autorisés, TTL des URLs signées, headers requis. '
            'Point d\'entrée pour les équipes qui intègrent le service.',
            '—',
            '200 OK\n{"service":"sendbid-storage","version":"1.0.0","categories":{"avatars":{"public":true,"max_size_mb":5,"allowed_mimes":[...]},...},"auth":{"required_header":"X-API-Key",...}}'
        ),
        (
            'GET', '/v1/metrics', 'Aucune',
            'Métriques au format Prometheus avec labels — disque total/libre/utilisé, '
            'taille et nombre de fichiers par catégorie, uptime.',
            '—',
            'sendbid_disk_used_gb 12.4\nsendbid_disk_free_gb 87.6\nsendbid_category_size_mb{category="kyc"} 234.5\nsendbid_uptime_seconds 3642\n...'
        ),
    ]

    for method, path, auth, description, request_ex, response_ex in endpoints:
        method_color = {'POST': 'F39C12', 'GET': '2ECC71', 'DELETE': 'E74C3C'}.get(method, '6C63FF')
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(12)

        run_m = p.add_run(f' {method} ')
        run_m.font.bold = True
        run_m.font.size = Pt(10)
        run_m.font.color.rgb = C_WHITE

        from docx.oxml import OxmlElement as OE
        rPr = run_m._r.get_or_add_rPr()
        shd = OE('w:shd')
        shd.set(qn('w:val'), 'clear')
        shd.set(qn('w:color'), 'auto')
        shd.set(qn('w:fill'), method_color)
        rPr.append(shd)

        run_p = p.add_run(f'  {path}')
        run_p.font.name = 'Courier New'
        run_p.font.bold = True
        run_p.font.size = Pt(11)
        run_p.font.color.rgb = RGBColor(0x2C, 0x3E, 0x50)

        run_a = p.add_run(f'    🔑 Auth: {auth}')
        run_a.font.size = Pt(9)
        run_a.font.color.rgb = C_MID_GREY

        desc_p = doc.add_paragraph(description)
        desc_p.paragraph_format.left_indent = Cm(0.5)
        desc_p.paragraph_format.space_before = Pt(2)
        desc_p.paragraph_format.space_after = Pt(2)
        desc_p.runs[0].font.size = Pt(10)

    doc.add_page_break()

    # ════════════════════════════════════════════════════════════
    # 7. SÉCURITÉ
    # ════════════════════════════════════════════════════════════
    h = doc.add_heading('7. Sécurité', level=1)
    style_heading(h, 1)
    add_horizontal_line(doc)

    h2 = doc.add_heading('7.1 Validation des fichiers uploadés', level=2)
    style_heading(h2, 2)

    add_styled_table(doc,
        headers=['Menace', 'Contre-mesure', 'Implémentation'],
        rows=[
            ['Faux type MIME', 'Détection par magic bytes (contenu réel)', 'file_validation.py → detect_mime_from_magic()'],
            ['Exécutables malveillants', 'Rejet si MZ (PE), ELF, #! (scripts)', 'is_dangerous_file() — vérifie les 8 premiers octets'],
            ['Fichiers trop volumineux', 'Limite par catégorie (5-10 MB)', 'max_sizes_bytes par catégorie dans config.py'],
            ['Path traversal', 'Nettoyage du nom client, UUID côté serveur', 'prevent_path_traversal() + UUID généré'],
            ['Métadonnées EXIF/GPS', 'Strip et ré-encodage via Pillow', 'strip_exif_and_reencode() — supprime GPS, device info'],
            ['Fichier vide', 'Rejet explicite', 'len(content) == 0 → 400'],
            ['MIME non whitelisté', 'Liste blanche par catégorie', 'allowed_mimes dans config.py'],
        ],
        col_widths=[4.0, 5.5, 7.0]
    )

    h2 = doc.add_heading('7.2 Contrôle d\'accès aux fichiers', level=2)
    style_heading(h2, 2)

    add_styled_table(doc,
        headers=['Cas', 'Accès autorisé ?', 'Code retour'],
        rows=[
            ['Propriétaire du fichier → son propre fichier', 'OUI', '200'],
            ['Autre utilisateur → fichier privé (KYC/reçu)', 'NON', '403 Forbidden'],
            ['Admin (role=admin) → n\'importe quel fichier', 'OUI', '200'],
            ['Agent KYC (role=kyc_agent) → n\'importe quel fichier', 'OUI', '200'],
            ['Sans authentification → n\'importe quel fichier', 'NON', '401 Unauthorized'],
            ['URL signée valide → fichier privé', 'OUI (temporaire)', '200'],
            ['URL signée expirée ou falsifiée', 'NON', '403 Forbidden'],
            ['URL publique /v1/public/ → fichier KYC', 'NON', '404 / 403'],
        ],
        col_widths=[8.0, 3.5, 5.0]
    )

    add_info_box(doc,
        'Le test de sécurité automatisé "KYC non accessible via URL publique" vérifie en permanence '
        'que /v1/public/avatars/ ne peut pas servir un fichier KYC, même si l\'attaquant connaît l\'UUID. '
        'Ce test fait partie de la suite pytest et doit être vert avant chaque déploiement.',
        color_hex='E74C3C', label='⚠  Test critique :')

    doc.add_page_break()

    # ════════════════════════════════════════════════════════════
    # 8. AUTH SERVICE-À-SERVICE
    # ════════════════════════════════════════════════════════════
    h = doc.add_heading('8. Authentification service-à-service', level=1)
    style_heading(h, 1)
    add_horizontal_line(doc)

    doc.add_paragraph(
        'Le Django backend communique avec le storage-service via HTTPS avec un double mécanisme d\'authentification :'
    )

    h2 = doc.add_heading('Headers HTTP requis', level=2)
    style_heading(h2, 2)

    add_styled_table(doc,
        headers=['Header', 'Obligatoire', 'Description'],
        rows=[
            ['X-API-Key',    'Toujours',             'Clé API partagée entre Django et storage-service'],
            ['X-Timestamp',  'Production',           'Timestamp Unix (tolérance ±30s pour éviter replay attacks)'],
            ['X-Signature',  'Production',           'HMAC-SHA256(api_key:timestamp:sha256(body), hmac_secret)'],
            ['X-User-Id',    'Recommandé',           'ID de l\'utilisateur final (transmis par Django)'],
            ['X-User-Role',  'Recommandé',           'Rôle : user | admin | kyc_agent'],
        ],
        col_widths=[4.0, 3.5, 9.0]
    )

    h2 = doc.add_heading('Calcul de la signature HMAC', level=2)
    style_heading(h2, 2)

    add_code_block(doc, """\
# Django côté → calcul de la signature
import hashlib, hmac, time

api_key    = settings.STORAGE_API_KEY
hmac_secret = settings.STORAGE_HMAC_SECRET
timestamp  = str(int(time.time()))
body       = b""  # pour multipart, body est vide

body_hash  = hashlib.sha256(body).hexdigest()
message    = f"{api_key}:{timestamp}:{body_hash}"
signature  = hmac.new(hmac_secret.encode(), message.encode(), hashlib.sha256).hexdigest()

headers = {
    "X-API-Key":   api_key,
    "X-Timestamp": timestamp,
    "X-Signature": signature,
    "X-User-Id":   str(request.user.id),
    "X-User-Role": request.user.role,
}""", caption='Exemple de calcul HMAC côté Django')

    doc.add_page_break()

    # ════════════════════════════════════════════════════════════
    # 9. GESTION PUBLICS vs SENSIBLES
    # ════════════════════════════════════════════════════════════
    h = doc.add_heading('9. Gestion des fichiers sensibles vs publics', level=1)
    style_heading(h, 1)
    add_horizontal_line(doc)

    add_styled_table(doc,
        headers=['Propriété', 'Avatars (publics)', 'KYC / Reçus (sensibles)'],
        rows=[
            ['Accès sans authentification', 'OUI — /v1/public/avatars/', 'JAMAIS — 403/404'],
            ['URL publique dans la réponse', 'OUI — CDN URL', 'NON — url: null'],
            ['Servi par Nginx directement', 'OUI (+ Cloudflare CDN)', 'NON — FastAPI uniquement'],
            ['Header Cache-Control', 'public, max-age=31536000', 'no-store, no-cache, private'],
            ['Audit log à l\'accès', 'Non (public)', 'OUI — chaque accès journalisé'],
            ['URL signée disponible', 'Non nécessaire', 'OUI — TTL 60s par défaut'],
            ['Contrôle propriétaire/rôle', 'Non (public)', 'OUI — strict'],
            ['Chiffrement au repos', 'Optionnel', 'Recommandé (LUKS ou applicatif)'],
        ],
        col_widths=[5.5, 5.5, 5.5]
    )

    add_info_box(doc,
        'Nginx est configuré avec un bloc location qui bloque EXPLICITEMENT '
        '/uploads/kyc/ et /uploads/receipts/ avec un return 403. '
        'Ce blocage est au niveau du serveur HTTP, indépendamment de FastAPI — couche de défense en profondeur.',
        color_hex='2ECC71', label='✅  Défense en profondeur :')

    doc.add_page_break()

    # ════════════════════════════════════════════════════════════
    # 10. NGINX
    # ════════════════════════════════════════════════════════════
    h = doc.add_heading('10. Configuration Nginx', level=1)
    style_heading(h, 1)
    add_horizontal_line(doc)

    add_code_block(doc, """\
# /etc/nginx/sites-available/sendbid-storage.conf

# ── CRITIQUE : Bloquer les dossiers sensibles en premier
location ~* ^/uploads/(kyc|receipts)/ {
    deny all;
    return 403 "Access denied";
}

# ── PUBLIC : Avatars servis directement depuis disque
location /v1/public/avatars/ {
    alias /var/app/uploads/avatars/;
    autoindex off;                          # Pas de listing !
    expires 1y;
    add_header Cache-Control "public, max-age=31536000, immutable";
    add_header X-Content-Type-Options "nosniff";
    limit_except GET HEAD { deny all; }
}

# ── PRIVÉ : Toutes les autres routes → FastAPI (auth requise)
location /v1/ {
    proxy_pass http://127.0.0.1:8080;
    add_header Cache-Control "no-store, no-cache, must-revalidate, private" always;
}

# Security headers globaux
add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
add_header X-Frame-Options "DENY" always;
add_header X-Content-Type-Options "nosniff" always;""",
    caption='Extraits clés de la config Nginx')

    doc.add_page_break()

    # ════════════════════════════════════════════════════════════
    # 11. SAUVEGARDE ET MONITORING
    # ════════════════════════════════════════════════════════════
    h = doc.add_heading('11. Scripts de sauvegarde et monitoring', level=1)
    style_heading(h, 1)
    add_horizontal_line(doc)

    h2 = doc.add_heading('11.1 Sauvegarde — scripts/backup.sh', level=2)
    style_heading(h2, 2)

    add_styled_table(doc,
        headers=['Paramètre', 'Valeur par défaut', 'Description'],
        rows=[
            ['UPLOAD_DIR',     '/var/app/uploads',           'Répertoire source à sauvegarder'],
            ['RESTIC_REPO',    'sftp:backup@.../backups/',   'Dépôt restic distant (SSH)'],
            ['RESTIC_PASSWORD_FILE', '/etc/sendbid/restic-password', 'Fichier contenant le mot de passe chiffrement'],
            ['KEEP_DAILY',     '7',                          'Conserver 7 snapshots quotidiens'],
            ['KEEP_WEEKLY',    '4',                          'Conserver 4 snapshots hebdomadaires'],
            ['KEEP_MONTHLY',   '3',                          'Conserver 3 snapshots mensuels'],
            ['SLACK_WEBHOOK',  '(optionnel)',                'Notification Slack en cas de succès/erreur'],
        ],
        col_widths=[5.0, 4.0, 7.5]
    )

    doc.add_paragraph()
    doc.add_paragraph('Planification (cron) :')
    add_code_block(doc, """\
# Crontab — exécuter en tant que sendbid
0 2 * * *   /opt/sendbid/scripts/backup.sh    # Backup quotidien à 2h
*/15 * * * * /opt/sendbid/scripts/monitor_disk.sh  # Vérif disque toutes les 15 min""",
    caption='Crontab recommandé')

    h2 = doc.add_heading('11.2 Monitoring disque — scripts/monitor_disk.sh', level=2)
    style_heading(h2, 2)

    doc.add_paragraph(
        'Le script vérifie le pourcentage d\'utilisation du disque. Si le seuil est dépassé '
        '(défaut : 80%), il envoie une alerte par email et/ou Slack. Exit code 2 si alerte déclenchée.'
    )

    add_info_box(doc,
        'L\'endpoint GET /health retourne également les métriques disque en temps réel. '
        'L\'UI de test affiche un badge "Alerte seuil" si le disque dépasse le seuil configuré.',
        color_hex='F39C12', label='ℹ  Monitoring :')

    doc.add_page_break()

    # ════════════════════════════════════════════════════════════
    # 12. MIGRATION
    # ════════════════════════════════════════════════════════════
    h = doc.add_heading('12. Script de migration depuis Emergent Storage', level=1)
    style_heading(h, 1)
    add_horizontal_line(doc)

    doc.add_paragraph(
        'Le script scripts/migrate_from_emergent.py permet de migrer tous les fichiers '
        'existants depuis Emergent Object Storage vers le nouveau service local, sans coupure de service.'
    )

    add_code_block(doc, """\
# Exécution de la migration
python scripts/migrate_from_emergent.py \\
    --emergent-base-url https://storage.emergent.example.com \\
    --emergent-api-key  YOUR_EMERGENT_KEY \\
    --storage-url       http://localhost:8080 \\
    --storage-api-key   your-sendbid-api-key \\
    --manifest          files_manifest.csv \\
    --dry-run           # Simuler d'abord, puis relancer sans --dry-run""",
    caption='Commande de migration')

    doc.add_paragraph()
    doc.add_paragraph('Format du fichier manifeste CSV :')
    add_code_block(doc, 'id,category,owner_user_id,url,checksum\nf3a8b2c1,...,avatars,user-001,https://emergent.../...,abc123sha256...')

    add_styled_table(doc,
        headers=['Fonctionnalité', 'Description'],
        rows=[
            ['Vérification checksum', 'SHA-256 vérifié après chaque téléchargement'],
            ['Mode dry-run', 'Simulation complète sans écriture — valider avant migration réelle'],
            ['Rapport JSON', 'migration_report.json avec tous les résultats (succès/échecs)'],
            ['Délai configurable', '--delay-seconds pour ne pas surcharger Emergent'],
            ['Reprise sur erreur', 'Les fichiers en erreur sont listés pour re-traitement'],
            ['Sans coupure', 'L\'ancien service continue de fonctionner pendant la migration'],
        ],
        col_widths=[5.0, 11.5]
    )

    doc.add_page_break()

    # ════════════════════════════════════════════════════════════
    # 13. INTÉGRATION DJANGO
    # ════════════════════════════════════════════════════════════
    h = doc.add_heading('13. Intégration Django (remplacement Emergent SDK)', level=1)
    style_heading(h, 1)
    add_horizontal_line(doc)

    doc.add_paragraph(
        'Le fichier django_integration/storage_client.py est un client HTTP '
        'qui remplace l\'ancien SDK Emergent Object Storage. Il gère automatiquement '
        'l\'authentification HMAC et l\'envoi de l\'identité utilisateur.'
    )

    add_code_block(doc, """\
# settings.py Django — ajouter :
STORAGE_BASE_URL   = env("STORAGE_BASE_URL",   default="http://localhost:8080")
STORAGE_API_KEY    = env("STORAGE_API_KEY",    default="dev-api-key-sendbid-2024")
STORAGE_HMAC_SECRET = env("STORAGE_HMAC_SECRET", default="dev-hmac-secret")

# Dans une vue Django :
from django_integration.storage_client import StorageClient, StorageError

client = StorageClient()

# Upload avatar
with open(file_obj, 'rb') as f:
    result = client.upload_avatar(f, owner_user_id=str(request.user.id))
    avatar_url = result["url"]                  # URL publique CDN

# Upload KYC (sensible)
with open(cni_file, 'rb') as f:
    result = client.upload_kyc(f, owner_user_id=str(request.user.id))
    file_id = result["file_id"]                 # Stocker l'ID en base Django

# Obtenir une URL signée (60s) pour afficher le KYC
signed_url = client.get_file_url(file_id, user_id=str(request.user.id), ttl=60)

# Supprimer un fichier
client.delete_file(file_id, user_id=str(request.user.id))""",
    caption='Usage du StorageClient dans Django')

    doc.add_page_break()

    # ════════════════════════════════════════════════════════════
    # 14. INTERFACE UTILISATEUR DE TEST
    # ════════════════════════════════════════════════════════════
    h = doc.add_heading('14. Interface utilisateur de test', level=1)
    style_heading(h, 1)
    add_horizontal_line(doc)

    doc.add_paragraph(
        'Une interface web complète est disponible sur http://localhost:8080/ui '
        '(fichier ui/index.html). Elle permet de tester toutes les fonctionnalités '
        'du service sans écrire de code.'
    )

    add_styled_table(doc,
        headers=['Section', 'Fonctionnalités'],
        rows=[
            ['Upload',              'Glisser-déposer, générateur de fichier test canvas, sélecteur catégorie, barre de progression'],
            ['Tests invalides',     'Boutons one-click : exécutable MZ, script shell, fichier vide, oversized, mauvaise catégorie'],
            ['Mes fichiers',        'Liste par user/rôle/catégorie avec actions : copier ID, accéder, supprimer'],
            ['Contrôle d\'accès',   'Tester qui peut accéder à un fichier : propriétaire, autre user, admin, sans auth'],
            ['URLs signées',        'Générer une URL signée, la tester, tester une URL falsifiée'],
            ['Tests sécurité',      '6 tests automatisés : KYC jamais public, reçu jamais public, auth requise, exécutable rejeté, URL falsifiée rejetée, health public'],
            ['Santé & métriques',   'Dashboard disque par catégorie, statut DB, badge alerte seuil'],
            ['Configuration',       'Changer base URL / API Key / user / rôle à la volée — persisté localStorage'],
        ],
        col_widths=[4.5, 12.0]
    )

    doc.add_page_break()

    # ════════════════════════════════════════════════════════════
    # 15. TESTS AUTOMATISÉS
    # ════════════════════════════════════════════════════════════
    h = doc.add_heading('15. Suite de tests automatisés', level=1)
    style_heading(h, 1)
    add_horizontal_line(doc)

    add_code_block(doc, """\
# Installer les dépendances de test
pip install pytest pytest-asyncio httpx aiosqlite

# Lancer tous les tests
cd sendbid-storage-service
pytest tests/ -v

# Lancer un fichier spécifique
pytest tests/test_security.py -v
pytest tests/test_upload.py -v""",
    caption='Commandes pour lancer les tests')

    add_styled_table(doc,
        headers=['Fichier', 'Tests', 'Description'],
        rows=[
            ['test_upload.py',         '10', 'Upload JPEG valide, PNG valide, PDF KYC, exécutable rejeté, script rejeté, vide rejeté, catégorie invalide, MIME wrong, sans auth, nom UUID'],
            ['test_access_control.py', '12', 'Owner→KYC, autre user refusé, admin accès tout, sans auth 401, méta, URL signée, URL signée valide fonctionne, URL falsifiée refusée, owner delete, autre user delete refusé, liste owner seulement, admin liste tout'],
            ['test_security.py',       '9',  'KYC non public, reçu non public, auth requise KYC, URL publique avatar OK, KYC pas d\'URL publique, reçu pas d\'URL, cache sensible no-store, cache avatar public, path traversal'],
        ],
        col_widths=[5.0, 1.8, 9.7]
    )

    add_info_box(doc,
        'Les tests utilisent une base SQLite en mémoire et un répertoire temporaire — '
        'aucune connexion externe n\'est requise. Chaque test s\'exécute dans un état propre.',
        color_hex='2ECC71', label='✅  Isolation :')

    doc.add_page_break()

    # ════════════════════════════════════════════════════════════
    # 16. DOCKER
    # ════════════════════════════════════════════════════════════
    h = doc.add_heading('16. Docker & déploiement', level=1)
    style_heading(h, 1)
    add_horizontal_line(doc)

    add_code_block(doc, """\
# Démarrer le service (PostgreSQL + storage-service)
docker-compose up -d

# Vérifier les logs
docker-compose logs -f storage

# Build manuel de l'image
docker build -t sendbid-storage:1.0.0 .

# Variables d'env requises en production
export API_KEY="votre-cle-api-securisee"
export HMAC_SECRET="votre-hmac-secret-securise"
export CDN_BASE_URL="https://storage.sendbid.com"
docker-compose up -d""",
    caption='Commandes Docker')

    doc.add_page_break()

    # ════════════════════════════════════════════════════════════
    # 17. CHECKLIST MISE EN PRODUCTION
    # ════════════════════════════════════════════════════════════
    h = doc.add_heading('17. Checklist de mise en production', level=1)
    style_heading(h, 1)
    add_horizontal_line(doc)

    categories_checklist = [
        ('Sécurité', [
            'Changer API_KEY et HMAC_SECRET (min 32 caractères aléatoires)',
            'Configurer HTTPS avec certificat Let\'s Encrypt',
            'Activer HSTS (Strict-Transport-Security) dans Nginx',
            'Configurer le firewall UFW (ports 80, 443, 22 uniquement)',
            'Vérifier que /uploads/kyc/ et /uploads/receipts/ renvoient 403 via URL directe',
            'Lancer le test de sécurité automatisé : pytest tests/test_security.py -v',
            'Audit des permissions Linux : chown sendbid:sendbid, chmod 750',
        ]),
        ('Configuration', [
            'Définir DATABASE_URL vers PostgreSQL (pas SQLite)',
            'Définir UPLOAD_ROOT vers /var/app/uploads',
            'Définir CDN_BASE_URL vers votre domaine Cloudflare',
            'Configurer APP_ENV=production (active la vérification HMAC obligatoire)',
            'Vérifier MAX_SIZE_AVATAR_MB, MAX_SIZE_KYC_MB, MAX_SIZE_RECEIPT_MB',
        ]),
        ('Sauvegarde', [
            'Initialiser le dépôt restic et configurer le mot de passe',
            'Tester une sauvegarde manuelle : sudo -u sendbid /opt/sendbid/scripts/backup.sh',
            'Ajouter le cron pour backup quotidien (2h du matin)',
            'Effectuer un test de restauration et documenter la procédure',
            'Configurer les alertes email/Slack',
        ]),
        ('Monitoring', [
            'Ajouter le cron monitor_disk.sh (*/15 * * * *)',
            'Vérifier l\'endpoint /health depuis l\'extérieur',
            'Configurer Uptime Robot ou équivalent sur /health',
            'Brancher /v1/metrics sur Prometheus / Grafana si disponible',
        ]),
        ('Migration', [
            'Préparer le fichier manifeste CSV depuis l\'export Emergent',
            'Lancer la migration en --dry-run et vérifier le rapport',
            'Lancer la migration réelle et valider les checksums',
            'Mettre à jour le backend Django pour utiliser StorageClient',
            'Tester en staging avant de couper Emergent',
        ]),
    ]

    for cat_name, items in categories_checklist:
        h2 = doc.add_heading(cat_name, level=2)
        style_heading(h2, 2)
        for item in items:
            p = doc.add_paragraph(style='List Bullet')
            run = p.add_run('☐  ' + item)
            run.font.size = Pt(10.5)

    doc.add_page_break()

    # ════════════════════════════════════════════════════════════
    # 18. VARIABLES D'ENVIRONNEMENT
    # ════════════════════════════════════════════════════════════
    h = doc.add_heading('18. Variables d\'environnement', level=1)
    style_heading(h, 1)
    add_horizontal_line(doc)

    add_styled_table(doc,
        headers=['Variable', 'Défaut (dev)', 'Description', 'Obligatoire prod'],
        rows=[
            ['APP_ENV',              'development', 'production active la vérif HMAC obligatoire', 'OUI'],
            ['APP_HOST',             '0.0.0.0',     'Interface d\'écoute',                          'NON'],
            ['APP_PORT',             '8080',         'Port du service',                              'NON'],
            ['BASE_URL',             'http://localhost:8080', 'URL publique du service (pour signed URLs)', 'OUI'],
            ['DATABASE_URL',         'sqlite+aiosqlite:///...', 'URL de connexion DB (asyncpg en prod)', 'OUI'],
            ['API_KEY',              'dev-api-key-...', 'Clé API service-à-service',                'OUI'],
            ['HMAC_SECRET',          'dev-hmac-...',  'Secret HMAC (min 32 chars)',                 'OUI'],
            ['HMAC_TIMESTAMP_TOLERANCE_SECONDS', '30', 'Tolérance pour replay attack protection',  'NON'],
            ['UPLOAD_ROOT',          './uploads',    'Répertoire racine des fichiers',              'OUI'],
            ['MAX_SIZE_AVATAR_MB',   '5',            'Taille max avatar (MB)',                      'NON'],
            ['MAX_SIZE_KYC_MB',      '10',           'Taille max KYC (MB)',                         'NON'],
            ['MAX_SIZE_RECEIPT_MB',  '10',           'Taille max reçu (MB)',                        'NON'],
            ['SIGNED_URL_TTL',       '60',           'Durée de vie URLs signées (secondes)',         'NON'],
            ['CDN_BASE_URL',         'http://localhost:8080', 'Base URL CDN pour avatars',          'OUI'],
            ['DISK_ALERT_THRESHOLD_PERCENT', '80',  'Seuil alerte disque (%)',                     'NON'],
        ],
        col_widths=[5.0, 4.5, 5.5, 2.5]
    )

    # ════════════════════════════════════════════════════════════
    # 19. ADAPTATION POUR L'INTÉGRATION
    # ════════════════════════════════════════════════════════════
    h = doc.add_heading('19. Adaptation pour l\'intégration — Contrat d\'API', level=1)
    style_heading(h, 1)
    add_horizontal_line(doc)

    doc.add_paragraph(
        'Le service a été adapté pour être consommé de manière fiable par d\'autres services '
        '(Django, React Native, systèmes de monitoring). Chaque réponse suit un contrat standardisé '
        'pour faciliter la gestion des erreurs côté client.'
    )

    # ── 19.1 Headers de service
    h2 = doc.add_heading('19.1 Headers de service — sur chaque réponse', level=2)
    style_heading(h2, 2)

    add_styled_table(doc,
        headers=['Header', 'Exemple', 'Description'],
        rows=[
            ['X-Request-ID',      '4c3e4993-d515-4dc5-ab45-778886a5b01f', 'UUID unique par requête — propagé si envoyé par le client (traçabilité end-to-end)'],
            ['X-Service-Version', '1.0.0',  'Version du service storage — utile pour détection de breaking changes'],
            ['X-Response-Time',   '12.5ms', 'Temps de traitement côté serveur — aide au monitoring des performances'],
        ],
        col_widths=[4.5, 5.5, 6.5]
    )

    add_code_block(doc, """\
# Exemple : envoyer un Request-ID depuis Django pour la traçabilité
import uuid, requests

trace_id = str(uuid.uuid4())
response = requests.post(
    f"{STORAGE_BASE_URL}/v1/files",
    headers={
        "X-API-Key": STORAGE_API_KEY,
        "X-User-Id": str(user.id),
        "X-Request-ID": trace_id,   # Sera renvoyé dans X-Request-ID de la réponse
    },
    files={"file": file_obj},
    data={"category": "kyc", "owner_user_id": str(user.id)},
)
# response.headers["X-Request-ID"] == trace_id
# response.headers["X-Response-Time"] == "8.3ms"
# response.headers["X-Service-Version"] == "1.0.0" """,
    caption='Propagation du Request-ID depuis Django')

    # ── 19.2 Enveloppe de réponse standardisée
    h2 = doc.add_heading('19.2 Enveloppe de réponse standardisée', level=2)
    style_heading(h2, 2)

    doc.add_paragraph('Toutes les réponses de succès retournent les champs métier directement (pas d\'enveloppe imbriquée). '
                      'Toutes les erreurs suivent le même format avec un code machine.')

    add_code_block(doc, """\
# ── SUCCÈS (201 pour upload, 200 pour les autres)
{
  "file_id":   "a3f8b2c1-4d5e-4f6a-b7c8-d9e0f1a2b3c4",
  "category":  "kyc",
  "size":      85432,
  "mime":      "application/pdf",
  "checksum":  "abc123def456...",
  "url":       null,       ← toujours null pour KYC/reçus, URL CDN pour avatars
  "public":    false,      ← nouveau champ — indique si le fichier est public
  "message":   "Upload successful"
}

# ── ERREUR (400, 401, 403, 404, 413, 422, 500)
{
  "success":    false,
  "request_id": "4c3e4993-d515-4dc5-ab45-778886a5b01f",
  "error":      "File is too large for category 'avatars' (max 5 MB)",
  "code":       "FILE_TOO_LARGE",    ← code machine — parser côté Django
  "detail":     "Received 6291456 bytes, max is 5242880",
  "field":      "file"               ← champ concerné (si erreur de validation)
}""",
    caption='Format des réponses succès et erreur')

    # ── 19.3 Codes d'erreur machine
    h2 = doc.add_heading('19.3 Codes d\'erreur — référence complète', level=2)
    style_heading(h2, 2)

    add_styled_table(doc,
        headers=['Code', 'HTTP', 'Déclencheur'],
        rows=[
            ['MISSING_API_KEY',        '401', 'Header X-API-Key absent'],
            ['INVALID_API_KEY',        '403', 'Header X-API-Key incorrect'],
            ['INVALID_HMAC',           '403', 'Signature HMAC invalide ou timestamp hors tolérance'],
            ['HMAC_REQUIRED',          '403', 'APP_ENV=production mais HMAC absent'],
            ['FORBIDDEN',              '403', 'Accès refusé (rôle insuffisant)'],
            ['EMPTY_FILE',             '400', 'Fichier de taille 0'],
            ['FILE_TOO_LARGE',         '413', 'Fichier dépasse la limite de la catégorie'],
            ['INVALID_MIME',           '400', 'Type MIME non autorisé pour cette catégorie'],
            ['DANGEROUS_FILE',         '400', 'Magic bytes dangereux : MZ (PE), ELF, script #!'],
            ['INVALID_CATEGORY',       '400', 'Catégorie inconnue ou contient des caractères suspects'],
            ['IMAGE_PROCESSING_ERROR', '400', 'Échec du ré-encodage Pillow'],
            ['FILE_NOT_FOUND',         '404', 'UUID inconnu ou fichier supprimé (is_deleted=True)'],
            ['ACCESS_DENIED',          '403', 'User non propriétaire, non admin, non kyc_agent'],
            ['SIGNED_URL_INVALID',     '403', 'Signature de l\'URL signée ne correspond pas'],
            ['SIGNED_URL_EXPIRED',     '403', 'Timestamp expires dans le passé'],
            ['INTERNAL_ERROR',         '500', 'Erreur serveur non anticipée'],
            ['DATABASE_ERROR',         '500', 'Échec de requête base de données'],
            ['STORAGE_ERROR',          '500', 'Erreur d\'écriture ou lecture sur disque'],
        ],
        col_widths=[5.5, 1.8, 9.2]
    )

    add_code_block(doc, """\
# Django — gestion des erreurs standardisée
import requests

def upload_kyc(file_obj, user_id):
    r = requests.post(
        f"{STORAGE_BASE_URL}/v1/files",
        headers={"X-API-Key": STORAGE_API_KEY, "X-User-Id": str(user_id)},
        files={"file": file_obj},
        data={"category": "kyc", "owner_user_id": str(user_id)},
    )
    if r.status_code == 201:
        return r.json()["file_id"]

    # Lecture du code machine pour une gestion précise
    err = r.json()
    code = err.get("code", "UNKNOWN")

    if code == "FILE_TOO_LARGE":
        raise ValidationError("Document trop volumineux (max 10 MB)")
    elif code == "INVALID_MIME":
        raise ValidationError("Format de fichier non accepté")
    elif code == "DANGEROUS_FILE":
        raise SecurityError("Fichier dangereux détecté")
    elif code == "MISSING_API_KEY":
        raise ConfigError("Clé API storage manquante — vérifier settings.py")
    else:
        raise StorageError(f"Erreur storage [{code}]: {err.get('error')}")""",
    caption='Gestion des codes d\'erreur côté Django')

    # ── 19.4 Nouveaux endpoints
    h2 = doc.add_heading('19.4 Nouveaux endpoints d\'intégration', level=2)
    style_heading(h2, 2)

    add_styled_table(doc,
        headers=['Endpoint', 'Auth', 'Usage recommandé'],
        rows=[
            ['GET /v1/ping',    'Non', 'Load-balancer health check, k8s livenessProbe — réponse < 5ms'],
            ['GET /health',     'Non', 'k8s readinessProbe, monitoring externe (Uptime Robot, Datadog)'],
            ['GET /v1/info',    'Non', 'Bootstrap de l\'intégration — récupère les limites et MIME autorisés'],
            ['GET /v1/metrics', 'Non', 'Prometheus scrape, Grafana dashboard — toutes les 15 secondes'],
        ],
        col_widths=[4.5, 1.8, 10.2]
    )

    add_info_box(doc,
        'Recommandation k8s : utiliser /v1/ping pour livenessProbe (failureThreshold=3, periodSeconds=10) '
        'et /health pour readinessProbe (failureThreshold=1, periodSeconds=30). '
        'Le ping ne frappe pas la DB — il ne fausse pas les métriques de disponibilité.',
        color_hex='6C63FF', label='☁  Déploiement cloud :')

    doc.add_page_break()

    # ════════════════════════════════════════════════════════════
    # 20. SUITE DE TESTS D'INTÉGRATION
    # ════════════════════════════════════════════════════════════
    h = doc.add_heading('20. Suite de tests d\'intégration — 107 cas', level=1)
    style_heading(h, 1)
    add_horizontal_line(doc)

    doc.add_paragraph(
        'La suite de tests d\'intégration couvre l\'ensemble des comportements attendus du service '
        'avant toute mise en production. Elle est exécutable depuis l\'UI de test (bouton "Lancer tous les tests") '
        'et documetée dans le fichier INTEGRATION_CHECKLIST.md. '
        'Les blocs 1 à 5 sont BLOQUANTS — un seul échec empêche la mise en production.'
    )

    add_info_box(doc,
        'Accéder à l\'interface de test : http://localhost:8080/ui → onglet "Intégration". '
        'Cliquer sur "Lancer tous les tests" pour exécuter les 55 cas automatisables en continu. '
        'Les 52 cas restants sont documentés dans INTEGRATION_CHECKLIST.md pour exécution manuelle ou Postman.',
        color_hex='2ECC71', label='▶  Interface :')

    # ── Résumé des blocs
    h2 = doc.add_heading('20.1 Résumé des 11 blocs', level=2)
    style_heading(h2, 2)

    add_styled_table(doc,
        headers=['Bloc', 'Description', 'Tests', 'Priorité', 'Auto'],
        rows=[
            ['Bloc 1',  'Infrastructure & connectivité — ping, health, headers, info, métriques',  '7',  '🔴 Critique',  '100%'],
            ['Bloc 2',  'Authentification — sans clé, clé invalide, clé valide, HMAC',             '4',  '🔴 Critique',  '80%'],
            ['Bloc 3A', 'Uploads valides — avatar, KYC, reçu, UUID, checksum, nom neutralisé',     '6',  '🔴 Critique',  '100%'],
            ['Bloc 3B', 'Uploads invalides — exécutable MZ, ELF, shell, vide, oversized, catégorie', '6', '🔴 Critique', '100%'],
            ['Bloc 4',  'Contrôle d\'accès — owner, tiers, admin, kyc_agent, sans auth, liste',   '7',  '🔴 Critique',  '100%'],
            ['Bloc 5',  'Sécurité CRITIQUE — KYC jamais public, url=null, Cache-Control, nosniff', '6', '🔴 Critique',  '100%'],
            ['Bloc 6',  'URLs signées — génération, download, expirée, falsifiée, sans auth',      '5',  '🟠 Important', '100%'],
            ['Bloc 7',  'Suppression — logique, 404 après delete, admin, double delete, tiers',    '3',  '🟠 Important', '100%'],
            ['Bloc 8',  'Contrat d\'API — headers, propagation ID, format erreur, Content-Type',   '5',  '🟠 Important', '100%'],
            ['Bloc 9',  'Health & Monitoring — DB down, disque > 80%, checks, uptime, Prometheus', '6',  '🟡 Modéré',   '60%'],
            ['Bloc 10-11', 'Intégration Django + Performance — client, timeout, uploads simultanés', '14', '🟡 Modéré', '70%'],
            ['TOTAL',   '',                                                                          '107', '',           '~90%'],
        ],
        col_widths=[2.2, 7.8, 1.5, 2.8, 1.5]
    )

    # ── Bloc 5 détaillé (le plus critique)
    h2 = doc.add_heading('20.2 Bloc 5 — Tests de sécurité CRITIQUES (détail)', level=2)
    style_heading(h2, 2)

    add_info_box(doc,
        'Ces 6 tests doivent être VERTS avant chaque déploiement. Un seul échec = faille RGPD potentielle.',
        color_hex='E74C3C', label='🔴  Bloquants :')

    add_styled_table(doc,
        headers=['ID', 'Test', 'Endpoint testé', 'Résultat attendu', 'Si échec'],
        rows=[
            ['5.1', 'KYC jamais accessible publiquement',
             'GET /v1/public/avatars/{kyc_id}',
             '403 ou 404 — JAMAIS 200',
             '🚨 FAILLE RGPD — CNI accessible sans auth'],
            ['5.2', 'Reçu jamais accessible publiquement',
             'GET /v1/public/avatars/{receipt_id}',
             '403 ou 404 — JAMAIS 200',
             '🚨 FAILLE — Reçu financier exposé'],
            ['5.3', 'Réponse KYC sans URL publique',
             'POST /v1/files [kyc] → champ url',
             'url: null dans la réponse',
             '🚨 URL publique divulguée'],
            ['5.4', 'Réponse reçu sans URL publique',
             'POST /v1/files [receipts] → champ url',
             'url: null dans la réponse',
             '🚨 URL publique divulguée'],
            ['5.5', 'Cache-Control no-store sur KYC',
             'GET /v1/files/{kyc_id} → header',
             'Cache-Control: no-store',
             '⚠ Fichier potentiellement mis en cache navigateur'],
            ['5.6', 'X-Content-Type-Options nosniff',
             'GET /v1/files/{id} → header',
             'X-Content-Type-Options: nosniff',
             '⚠ MIME sniffing possible côté navigateur'],
        ],
        col_widths=[1.2, 4.2, 4.2, 3.5, 3.5]
    )

    # ── Bloc 8 détaillé (contrat API)
    h2 = doc.add_heading('20.3 Bloc 8 — Contrat d\'API (détail)', level=2)
    style_heading(h2, 2)

    add_styled_table(doc,
        headers=['ID', 'Test', 'Vérification', 'Attendu'],
        rows=[
            ['8.1', 'X-Request-ID sur chaque réponse',        'GET /v1/ping → headers',           'UUID v4 format présent'],
            ['8.2', 'X-Service-Version présent',              'GET /v1/ping → headers',           '"1.0.0"'],
            ['8.3', 'Propagation X-Request-ID client',        'Envoyer X-Request-ID: my-id',      'Retourné identique en réponse'],
            ['8.4', 'Format erreur standardisé',              'GET /v1/files sans auth',          '{"success":false,"code":"...","error":"..."}'],
            ['8.5', 'Content-Type application/json',          'GET /health → headers',            '"application/json; charset=utf-8"'],
        ],
        col_widths=[1.2, 5.0, 5.0, 5.5]
    )

    # ── Commandes CURL de référence
    h2 = doc.add_heading('20.4 Commandes cURL de référence', level=2)
    style_heading(h2, 2)

    add_code_block(doc, """\
BASE="http://localhost:8080"
KEY="dev-api-key-sendbid-2024"
UID="user-001"

# 1. Liveness probe
curl -s $BASE/v1/ping | python -m json.tool

# 2. Headers de service (vérifier X-Request-ID, X-Service-Version, X-Response-Time)
curl -si $BASE/v1/ping | grep -E "X-Request-ID|X-Service-Version|X-Response-Time"

# 3. Contrat d'API (limites, MIME, TTL)
curl -s $BASE/v1/info | python -m json.tool

# 4. Upload avatar
curl -s -X POST $BASE/v1/files \\
  -H "X-API-Key: $KEY" -H "X-User-Id: $UID" -H "X-User-Role: user" \\
  -F "file=@avatar.jpg" -F "category=avatars" | python -m json.tool

# 5. Test sécurité critique — KYC via URL publique (doit retourner 403 ou 404)
curl -s -o /dev/null -w "%{http_code}" "$BASE/v1/public/avatars/{KYC_FILE_ID}"

# 6. URL signée
curl -s "$BASE/v1/files/{FILE_ID}/signed?ttl=60" \\
  -H "X-API-Key: $KEY" -H "X-User-Id: $UID" | python -m json.tool

# 7. Propagation Request-ID
curl -si $BASE/v1/ping -H "X-Request-ID: mon-trace-id-123" | grep X-Request-ID

# 8. Test exécutable rejeté (attendu 400)
python3 -c "import sys; sys.stdout.buffer.write(b'MZ'+'\\x00'*100)" > /tmp/virus.exe
curl -s -X POST $BASE/v1/files \\
  -H "X-API-Key: $KEY" -H "X-User-Id: $UID" \\
  -F "file=@/tmp/virus.exe" -F "category=avatars" | python -m json.tool""",
    caption='Commandes cURL pour les tests d\'intégration')

    # ── Procédure de validation avant mise en production
    h2 = doc.add_heading('20.5 Procédure de validation avant mise en production', level=2)
    style_heading(h2, 2)

    for step, desc in [
        ('Étape 1 — Liveness', 'Vérifier que GET /v1/ping retourne 200 {"pong":true} — si échec, le service ne répond pas'),
        ('Étape 2 — Readiness', 'Vérifier que GET /health retourne {"status":"ok"} — si "degraded", corriger DB ou disque avant de continuer'),
        ('Étape 3 — Sécurité critique (Bloc 5)', 'Lancer les 6 tests sécurité depuis l\'UI → onglet Intégration. Tous doivent être verts. Aucune exception.'),
        ('Étape 4 — Authentification (Bloc 2)', 'Vérifier que sans X-API-Key on reçoit 401, et avec une mauvaise clé on reçoit 403'),
        ('Étape 5 — Upload + Contrat', 'Uploader un avatar et vérifier : url présent, public:true. Uploader un KYC et vérifier : url=null, public:false'),
        ('Étape 6 — Contrat API (Bloc 8)', 'Vérifier que X-Request-ID, X-Service-Version et X-Response-Time sont présents dans chaque réponse'),
        ('Étape 7 — Tests automatisés pytest', 'Exécuter pytest tests/ -v — tous les tests doivent passer'),
        ('Étape 8 — Rapport', 'Documenter les résultats avec les Request-IDs des tests dans le registre de déploiement'),
    ]:
        h3 = doc.add_heading(step, level=3)
        style_heading(h3, 3)
        p = doc.add_paragraph(desc)
        p.paragraph_format.left_indent = Cm(0.5)
        p.runs[0].font.size = Pt(10.5)

    doc.add_page_break()

    # ════════════════════════════════════════════════════════════
    # 21. GUIDE D'INTÉGRATION — FONCTIONNEMENT DE L'API
    # ════════════════════════════════════════════════════════════
    h = doc.add_heading('21. Guide d\'intégration — Fonctionnement de l\'API', level=1)
    style_heading(h, 1)
    add_horizontal_line(doc)

    doc.add_paragraph(
        'Cette section explique comment fonctionne le service de stockage SENDBID et comment '
        'l\'intégrer dans n\'importe quelle application — mobile, web ou backend.'
    )

    # ── 21.1 Vue d'ensemble
    h2 = doc.add_heading('21.1 Vue d\'ensemble — Comment fonctionne le service', level=2)
    style_heading(h2, 2)

    doc.add_paragraph(
        'Le storage-service est un microservice HTTP indépendant. Il reçoit des fichiers, '
        'les valide, les stocke sur disque et les sert de façon sécurisée. '
        'Votre application (Django, React Native, site web) communique avec lui via des requêtes HTTP standard.'
    )

    add_code_block(doc, """\
Votre application                  Storage Service
      │                                   │
      │  POST /v1/files (multipart)       │
      │──────────────────────────────────►│  1. Reçoit le fichier
      │                                   │  2. Vérifie magic bytes + MIME
      │                                   │  3. Strip EXIF/GPS (images)
      │                                   │  4. Génère un UUID (jamais le nom client)
      │                                   │  5. Sauvegarde sur disque
      │                                   │  6. Enregistre métadonnées en base
      │  201 { file_id, checksum, url }   │
      │◄──────────────────────────────────│
      │                                   │
      │  (stocker file_id dans votre DB)  │
      │                                   │
      │  GET /v1/files/{file_id}/signed   │  Pour accéder plus tard à un fichier sensible
      │──────────────────────────────────►│
      │  200 { signed_url, expires_at }   │
      │◄──────────────────────────────────│
      │                                   │
      │  GET signed_url (sans auth)       │  L'URL fonctionne pendant 60 secondes
      │──────────────────────────────────►│
      │  200 — binaire du fichier         │
      │◄──────────────────────────────────│""",
    caption='Flux général d\'utilisation du storage-service')

    # ── 21.2 Principe des 3 types de fichiers
    h2 = doc.add_heading('21.2 Les 3 catégories et leurs comportements', level=2)
    style_heading(h2, 2)

    add_styled_table(doc,
        headers=['Catégorie', 'Qui l\'upload ?', 'Accès public ?', 'Ce que vous recevez', 'Comment l\'afficher'],
        rows=[
            ['avatars',
             'Utilisateur (photo de profil)',
             'OUI — sans auth',
             'url: "http://cdn.../v1/public/avatars/uuid"\npublic: true',
             'Mettre l\'url directement dans une balise <img> ou Image React Native'],
            ['kyc',
             'Utilisateur (CNI, passeport)',
             'NON — jamais',
             'url: null\npublic: false\nfile_id: "uuid"',
             'Stocker le file_id → demander une URL signée (60s) au moment de l\'affichage'],
            ['receipts',
             'Système (après transaction)',
             'NON — jamais',
             'url: null\npublic: false\nfile_id: "uuid"',
             'Idem KYC — URL signée à la demande'],
        ],
        col_widths=[2.2, 3.8, 2.0, 4.2, 4.3]
    )

    add_info_box(doc,
        'Règle essentielle : stocker le file_id dans votre base de données '
        '(table users, transactions…), jamais l\'URL complète pour les fichiers sensibles. '
        'L\'URL signée est générée à la demande et expire après 60 secondes.',
        color_hex='6C63FF', label='ℹ  Règle d\'or :')

    # ── 21.3 Authentification étape par étape
    h2 = doc.add_heading('21.3 Authentification — étape par étape', level=2)
    style_heading(h2, 2)

    doc.add_paragraph(
        'Toutes les requêtes vers /v1/ nécessitent 3 headers minimum :'
    )

    add_styled_table(doc,
        headers=['Header', 'Valeur', 'Obligatoire ?', 'Rôle'],
        rows=[
            ['X-API-Key',    'dev-api-key-sendbid-2024',    'Toujours',       'Clé secrète partagée entre votre backend et le service'],
            ['X-User-Id',    'user-001 (ID de l\'utilisateur)', 'Recommandé', 'Permet au service de savoir qui fait la requête'],
            ['X-User-Role',  'user | admin | kyc_agent',    'Recommandé',     'Détermine les droits d\'accès aux fichiers'],
            ['X-Timestamp',  '1728385886',                  'Production',     'Timestamp Unix — protection anti-replay'],
            ['X-Signature',  'hmac-sha256-hex…',            'Production',     'Preuve que la requête vient bien de votre backend'],
        ],
        col_widths=[3.2, 4.2, 2.5, 6.6]
    )

    add_info_box(doc,
        'Important : le header X-API-Key ne doit JAMAIS être envoyé depuis une application mobile '
        'ou un navigateur web directement. Il doit transiter uniquement par votre backend Django/API. '
        'L\'application mobile appelle votre Django, et Django appelle le storage-service.',
        color_hex='E74C3C', label='⚠  Sécurité :')

    # ── 21.4 Architecture d'intégration recommandée
    h2 = doc.add_heading('21.4 Architecture d\'intégration recommandée', level=2)
    style_heading(h2, 2)

    add_code_block(doc, """\
Application Mobile / Site Web
         │
         │  (1) L'utilisateur choisit un fichier
         │
         ▼
 Backend Django (votre API)         ←── X-API-Key reste ici, côté serveur
         │
         │  (2) Django valide, puis appelle le storage-service
         │
         ▼
 Storage Service (SENDBID)
         │
         │  (3) Stocke et retourne file_id + éventuellement url
         │
         ▼
 Backend Django
         │
         │  (4) Enregistre file_id dans sa propre base de données
         │      Retourne à l'app : { file_id, url (si avatar) }
         │
         ▼
Application Mobile / Site Web
         │
         │  (5a) Avatar → afficher url directement (public CDN)
         │  (5b) KYC   → demander à Django une URL signée → afficher
         │""",
    caption='Architecture recommandée — la clé API ne quitte jamais le backend')

    # ── 21.5 Flux complets
    h2 = doc.add_heading('21.5 Flux complets par cas d\'usage', level=2)
    style_heading(h2, 2)

    for titre, flux in [
        ('Cas 1 — Upload et affichage d\'un avatar', """\
App Mobile                    Django Backend               Storage Service
    │                               │                            │
    │── POST /api/upload-avatar ───►│                            │
    │   (multipart, token JWT)       │                            │
    │                               │── POST /v1/files ─────────►│
    │                               │   X-API-Key + X-User-Id    │
    │                               │   category=avatars          │ Valide
    │                               │                            │ Strip EXIF
    │                               │◄── 201 { file_id, url } ───│ Sauvegarde
    │                               │                            │
    │                               │  Sauvegarde url en base    │
    │◄── 200 { avatar_url } ────────│                            │
    │                               │                            │
    │── <Image source={{ uri: avatar_url }} />                   │
    │   L'image se charge directement depuis le CDN              │"""),
        ('Cas 2 — Upload et consultation d\'un document KYC', """\
App Mobile                    Django Backend               Storage Service
    │                               │                            │
    │── POST /api/upload-kyc ──────►│                            │
    │                               │── POST /v1/files ─────────►│
    │                               │   category=kyc              │
    │                               │◄── 201 { file_id, url:null}─│
    │                               │                            │
    │                               │  Sauvegarde file_id en base│
    │◄── 200 { kyc_id } ───────────│  (PAS l'url — elle est null)│
    │                               │                            │
    │  (plus tard — agent veut voir le KYC)                      │
    │                               │                            │
    │── GET /api/kyc/{kyc_id} ─────►│                            │
    │                               │── GET /v1/files/{file_id}──►│
    │                               │      /signed?ttl=60        │
    │                               │◄── 200 { signed_url } ─────│
    │◄── 200 { signed_url } ────────│                            │
    │                               │                            │
    │── Ouvre signed_url dans WebView/navigateur (60 secondes)   │"""),
    ]:
        h3 = doc.add_heading(titre, level=3)
        style_heading(h3, 3)
        add_code_block(doc, flux)

    doc.add_page_break()

    # ════════════════════════════════════════════════════════════
    # 22. INTÉGRATION REACT NATIVE
    # ════════════════════════════════════════════════════════════
    h = doc.add_heading('22. Intégration React Native (application mobile)', level=1)
    style_heading(h, 1)
    add_horizontal_line(doc)

    doc.add_paragraph(
        'Dans une application React Native, l\'application mobile ne communique JAMAIS directement '
        'avec le storage-service. Elle passe toujours par votre backend Django qui détient la clé API. '
        'Les exemples ci-dessous montrent la couche côté React Native et la couche côté Django.'
    )

    add_info_box(doc,
        'Dépendances React Native recommandées :\n'
        '• expo-image-picker ou react-native-image-picker (sélection fichier)\n'
        '• expo-file-system ou react-native-fs (lecture fichier)\n'
        '• axios ou fetch natif (requêtes HTTP)\n'
        '• expo-web-browser ou react-native-webview (affichage URL signée)',
        color_hex='6C63FF', label='📦  Dépendances :')

    # ── 22.1 Upload avatar
    h2 = doc.add_heading('22.1 Upload d\'un avatar (photo de profil)', level=2)
    style_heading(h2, 2)

    add_code_block(doc, """\
// ── services/storageService.js (React Native)
// L'app appelle VOTRE backend Django, pas le storage-service directement

import * as ImagePicker from 'expo-image-picker';

/**
 * Permet à l'utilisateur de choisir une photo depuis sa galerie
 * puis l'envoie à votre backend Django qui la transmet au storage-service.
 */
export async function uploadAvatar(userToken) {
  // 1. Ouvrir le sélecteur d'image
  const result = await ImagePicker.launchImageLibraryAsync({
    mediaTypes: ImagePicker.MediaTypeOptions.Images,
    allowsEditing: true,
    aspect: [1, 1],     // Carré pour les avatars
    quality: 0.85,      // Compression légère
  });

  if (result.canceled) return null;

  const asset = result.assets[0];

  // 2. Construire le FormData
  const formData = new FormData();
  formData.append('file', {
    uri: asset.uri,           // URI locale du fichier
    name: 'avatar.jpg',       // Le nom n'a pas d'importance (UUID côté serveur)
    type: asset.mimeType || 'image/jpeg',
  });
  // Pas besoin d'envoyer category — votre endpoint Django le fixe à 'avatars'

  // 3. Envoyer à VOTRE backend Django
  const response = await fetch('https://api.sendbid.com/users/avatar/', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${userToken}`,  // Votre JWT utilisateur
      'Content-Type': 'multipart/form-data',
    },
    body: formData,
  });

  if (!response.ok) {
    const err = await response.json();
    throw new Error(err.message || 'Erreur upload avatar');
  }

  const data = await response.json();
  // data.avatar_url = URL publique CDN, ex: http://cdn.sendbid.com/v1/public/avatars/uuid
  return data.avatar_url;
}

// ── Utilisation dans un composant React Native
import { Image, TouchableOpacity, Alert } from 'react-native';
import { useState } from 'react';

function ProfileScreen({ userToken, currentAvatarUrl }) {
  const [avatarUrl, setAvatarUrl] = useState(currentAvatarUrl);

  const handleChangeAvatar = async () => {
    try {
      const newUrl = await uploadAvatar(userToken);
      if (newUrl) {
        setAvatarUrl(newUrl);  // Mise à jour immédiate de l'affichage
        Alert.alert('Succès', 'Photo de profil mise à jour !');
      }
    } catch (error) {
      Alert.alert('Erreur', error.message);
    }
  };

  return (
    <TouchableOpacity onPress={handleChangeAvatar}>
      {/* L'avatar public se charge directement depuis le CDN */}
      <Image
        source={{ uri: avatarUrl }}
        style={{ width: 100, height: 100, borderRadius: 50 }}
      />
    </TouchableOpacity>
  );
}""",
    caption='React Native — Upload avatar via backend Django')

    # ── 22.2 Upload KYC
    h2 = doc.add_heading('22.2 Upload d\'un document KYC (CNI / Passeport)', level=2)
    style_heading(h2, 2)

    add_code_block(doc, """\
// ── services/kycService.js (React Native)

import * as DocumentPicker from 'expo-document-picker';

/**
 * L'utilisateur choisit son document d'identité (JPEG ou PDF).
 * L'app envoie à Django, Django transmet au storage-service.
 * Seul le file_id est retourné — jamais d'URL publique.
 */
export async function uploadKycDocument(userToken) {
  // 1. Ouvrir le sélecteur de document (PDF ou image)
  const result = await DocumentPicker.getDocumentAsync({
    type: ['image/jpeg', 'image/png', 'application/pdf'],
    copyToCacheDirectory: true,
  });

  if (result.canceled) return null;

  const doc = result.assets[0];

  // Vérification côté client (la validation réelle est faite côté serveur)
  if (doc.size > 10 * 1024 * 1024) {
    throw new Error('Le document est trop volumineux (max 10 MB)');
  }

  // 2. Construire le FormData
  const formData = new FormData();
  formData.append('document', {
    uri: doc.uri,
    name: doc.name,
    type: doc.mimeType,
  });

  // 3. Envoyer à VOTRE backend Django
  const response = await fetch('https://api.sendbid.com/kyc/upload/', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${userToken}`,
    },
    body: formData,
  });

  if (!response.ok) {
    const err = await response.json();
    // Gestion des erreurs métier
    if (err.code === 'FILE_TOO_LARGE')  throw new Error('Document trop volumineux (max 10 MB)');
    if (err.code === 'INVALID_MIME')    throw new Error('Format non accepté. Utilisez JPEG, PNG ou PDF.');
    if (err.code === 'DANGEROUS_FILE')  throw new Error('Ce fichier ne peut pas être envoyé.');
    throw new Error('Erreur lors de l\'envoi du document');
  }

  const data = await response.json();
  // data = { kyc_id: "uuid", status: "pending_review" }
  // Stocker kyc_id dans AsyncStorage ou l'état global (Redux, Zustand…)
  return data;
}

// ── Affichage du statut KYC dans l'application
function KycStatusScreen({ kycId, userToken }) {
  const [kycUrl, setKycUrl] = useState(null);

  // Pour les agents KYC — demander une URL signée temporaire via Django
  const viewDocument = async () => {
    const response = await fetch(`https://api.sendbid.com/kyc/${kycId}/view/`, {
      headers: { 'Authorization': `Bearer ${userToken}` }
    });
    const data = await response.json();
    // data.signed_url est valable 60 secondes
    setKycUrl(data.signed_url);
  };

  return (
    <View>
      <Button title="Voir le document" onPress={viewDocument} />
      {kycUrl && (
        // Ouvrir dans le navigateur intégré — s'efface après 60s
        <WebView source={{ uri: kycUrl }} style={{ height: 400 }} />
      )}
    </View>
  );
}""",
    caption='React Native — Upload KYC + affichage via URL signée')

    # ── 22.3 Backend Django côté mobile
    h2 = doc.add_heading('22.3 Côté Django — endpoints appelés par l\'app mobile', level=2)
    style_heading(h2, 2)

    add_code_block(doc, """\
# ── views.py Django — endpoints consommés par React Native

from django.views import View
from django.http import JsonResponse
from django_integration.storage_client import StorageClient, StorageError
import json

storage = StorageClient()

class AvatarUploadView(View):
    \"\"\"POST /users/avatar/ — appelé par l'app React Native\"\"\"

    def post(self, request):
        user = request.user  # JWT décodé par middleware
        file = request.FILES.get('file')

        if not file:
            return JsonResponse({'error': 'Fichier manquant'}, status=400)

        try:
            # Django appelle le storage-service avec la clé API (jamais exposée à l'app)
            result = storage.upload_avatar(file, owner_user_id=str(user.id))

            # Sauvegarder l'URL CDN dans le profil utilisateur
            user.profile.avatar_url = result['url']
            user.profile.save()

            # Retourner l'URL à l'app mobile — elle est publique, c'est OK
            return JsonResponse({'avatar_url': result['url']}, status=200)

        except StorageError as e:
            return JsonResponse({'message': str(e), 'code': e.code}, status=400)


class KycUploadView(View):
    \"\"\"POST /kyc/upload/ — appelé par l'app React Native\"\"\"

    def post(self, request):
        user = request.user
        document = request.FILES.get('document')

        if not document:
            return JsonResponse({'error': 'Document manquant'}, status=400)

        try:
            result = storage.upload_kyc(document, owner_user_id=str(user.id))

            # Stocker UNIQUEMENT le file_id en base — jamais d'URL (il n'y en a pas)
            kyc_record = KycDocument.objects.create(
                user=user,
                file_id=result['file_id'],   # UUID du storage-service
                status='pending_review',
            )
            return JsonResponse({'kyc_id': str(kyc_record.id), 'status': 'pending_review'}, status=201)

        except StorageError as e:
            return JsonResponse({'message': str(e), 'code': e.code}, status=400)


class KycViewUrlView(View):
    \"\"\"GET /kyc/{kyc_id}/view/ — génère une URL signée (60s) pour consulter un KYC\"\"\"

    def get(self, request, kyc_id):
        user = request.user
        kyc_record = KycDocument.objects.get(id=kyc_id)

        # Vérifier que l'utilisateur a le droit de voir ce document
        if not (user == kyc_record.user or user.role in ['admin', 'kyc_agent']):
            return JsonResponse({'error': 'Accès refusé'}, status=403)

        try:
            # Demander une URL signée valable 60 secondes
            signed_url = storage.get_file_url(
                file_id=kyc_record.file_id,
                user_id=str(user.id),
                ttl=60,
            )
            return JsonResponse({'signed_url': signed_url}, status=200)

        except StorageError as e:
            return JsonResponse({'error': str(e)}, status=500)""",
    caption='Django — endpoints backend pour l\'app mobile')

    doc.add_page_break()

    # ════════════════════════════════════════════════════════════
    # 23. INTÉGRATION WEB — JAVASCRIPT / REACT / VUE
    # ════════════════════════════════════════════════════════════
    h = doc.add_heading('23. Intégration Web — JavaScript / React / Vue', level=1)
    style_heading(h, 1)
    add_horizontal_line(doc)

    doc.add_paragraph(
        'Pour une application web (SPA React, Vue, ou page HTML classique), '
        'le même principe s\'applique : le navigateur envoie les fichiers à votre backend Django, '
        'qui les transmet au storage-service. La clé API ne doit jamais apparaître dans le code JavaScript envoyé au navigateur.'
    )

    # ── 23.1 Upload avatar (React)
    h2 = doc.add_heading('23.1 Upload d\'un avatar — React (JSX)', level=2)
    style_heading(h2, 2)

    add_code_block(doc, """\
// ── components/AvatarUploader.jsx

import { useState, useRef } from 'react';

export default function AvatarUploader({ userId, authToken, onSuccess }) {
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState(null);
  const inputRef = useRef();

  // Prévisualisation locale avant upload
  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (!file) return;

    // Validation simple côté client (la vraie validation est côté serveur)
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
      setError('Format non accepté. Utilisez JPEG, PNG ou WebP.');
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      setError('Image trop grande (max 5 MB).');
      return;
    }

    setError(null);
    setPreview(URL.createObjectURL(file));  // Affichage local immédiat
  };

  const handleUpload = async () => {
    const file = inputRef.current.files[0];
    if (!file) return;

    setLoading(true);
    const formData = new FormData();
    formData.append('file', file);  // Votre backend Django attend ce champ

    try {
      // Appel à VOTRE backend Django (pas au storage-service directement)
      const res = await fetch('/api/users/avatar/', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${authToken}` },
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.message || `Erreur ${res.status}`);
      }

      const data = await res.json();
      // data.avatar_url = URL CDN publique permanente
      onSuccess(data.avatar_url);  // Callback parent — met à jour l'affichage

    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="avatar-uploader">
      {/* Prévisualisation */}
      {preview && (
        <img src={preview} alt="Aperçu" style={{ width: 100, height: 100, borderRadius: '50%' }} />
      )}

      <input ref={inputRef} type="file" accept="image/jpeg,image/png,image/webp"
             onChange={handleFileChange} style={{ display: 'none' }} />

      <button onClick={() => inputRef.current.click()} disabled={loading}>
        Choisir une photo
      </button>

      <button onClick={handleUpload} disabled={loading || !preview}>
        {loading ? 'Envoi...' : 'Valider'}
      </button>

      {error && <p style={{ color: 'red' }}>{error}</p>}
    </div>
  );
}

// ── Affichage d'un avatar public (CDN) — simple balise img
function Avatar({ avatarUrl, size = 48 }) {
  return (
    <img
      src={avatarUrl}                    // URL CDN — charge sans auth
      alt="Avatar"
      width={size} height={size}
      style={{ borderRadius: '50%' }}
      onError={(e) => { e.target.src = '/default-avatar.png'; }}
    />
  );
}""",
    caption='React — Upload avatar et affichage via CDN')

    # ── 23.2 Upload KYC (Vue)
    h2 = doc.add_heading('23.2 Upload et consultation d\'un KYC — Vue 3 (Composition API)', level=2)
    style_heading(h2, 2)

    add_code_block(doc, """\
<!-- ── components/KycUploader.vue -->
<template>
  <div class="kyc-uploader">
    <label>Document d'identité (JPEG, PNG ou PDF — max 10 MB)</label>

    <input type="file" accept="image/jpeg,image/png,application/pdf"
           @change="onFileChange" :disabled="loading" />

    <div v-if="selectedFile" class="file-preview">
      <span>{{ selectedFile.name }}</span>
      <span>{{ (selectedFile.size / 1024 / 1024).toFixed(2) }} MB</span>
    </div>

    <button @click="uploadKyc" :disabled="!selectedFile || loading">
      {{ loading ? 'Envoi en cours...' : 'Envoyer le document' }}
    </button>

    <div v-if="error" class="error-msg">{{ error }}</div>
    <div v-if="successMsg" class="success-msg">{{ successMsg }}</div>

    <!-- Bouton pour visualiser le document (agents KYC uniquement) -->
    <button v-if="kycId && userRole === 'kyc_agent'" @click="viewDocument">
      Consulter le document
    </button>

    <!-- Affichage dans une iframe — URL expire après 60s -->
    <iframe v-if="signedUrl" :src="signedUrl"
            style="width:100%; height:500px; border:1px solid #ddd;" />
  </div>
</template>

<script setup>
import { ref } from 'vue';
import { useAuthStore } from '@/stores/auth';

const auth       = useAuthStore();
const loading    = ref(false);
const error      = ref(null);
const successMsg = ref(null);
const selectedFile = ref(null);
const kycId      = ref(null);
const signedUrl  = ref(null);

// Validation côté client
function onFileChange(event) {
  const file = event.target.files[0];
  error.value = null;

  if (!file) return;
  if (file.size > 10 * 1024 * 1024) {
    error.value = 'Fichier trop volumineux (max 10 MB)';
    return;
  }
  if (!['image/jpeg', 'image/png', 'application/pdf'].includes(file.type)) {
    error.value = 'Format non accepté. Utilisez JPEG, PNG ou PDF.';
    return;
  }
  selectedFile.value = file;
}

// Upload vers Django backend
async function uploadKyc() {
  loading.value = true;
  const formData = new FormData();
  formData.append('document', selectedFile.value);

  try {
    const res = await fetch('/api/kyc/upload/', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${auth.token}` },
      body: formData,
    });

    if (!res.ok) {
      const err = await res.json();
      // Lecture du code machine pour message précis
      const messages = {
        'FILE_TOO_LARGE':  'Document trop volumineux (max 10 MB)',
        'INVALID_MIME':    'Format non accepté par le serveur',
        'DANGEROUS_FILE':  'Ce fichier a été refusé pour raisons de sécurité',
      };
      throw new Error(messages[err.code] || err.message || 'Erreur serveur');
    }

    const data = await res.json();
    kycId.value      = data.kyc_id;
    successMsg.value = 'Document envoyé avec succès. En attente de vérification.';

  } catch (err) {
    error.value = err.message;
  } finally {
    loading.value = false;
  }
}

// Génère une URL signée pour consulter le document (60 secondes)
async function viewDocument() {
  const res = await fetch(`/api/kyc/${kycId.value}/view/`, {
    headers: { 'Authorization': `Bearer ${auth.token}` }
  });
  const data = await res.json();
  signedUrl.value = data.signed_url;

  // L'URL expire dans 60s — effacer l'iframe après
  setTimeout(() => { signedUrl.value = null; }, 58000);
}
</script>""",
    caption='Vue 3 — Upload KYC + consultation via URL signée')

    # ── 23.3 JavaScript vanilla
    h2 = doc.add_heading('23.3 JavaScript vanilla (sans framework)', level=2)
    style_heading(h2, 2)

    add_code_block(doc, """\
// ── storage.js — utilitaire générique (vanilla JS)
// Fonctionne dans n'importe quelle page HTML

const API_BASE = 'https://api.sendbid.com';  // Votre backend Django

/**
 * Upload un fichier via le backend Django.
 * @param {File}   file       - Objet File du navigateur
 * @param {string} endpoint   - '/api/users/avatar/' | '/api/kyc/upload/'
 * @param {string} authToken  - JWT de l'utilisateur
 * @returns {Promise<Object>} - Réponse JSON du backend
 */
async function uploadFile(file, endpoint, authToken) {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(`${API_BASE}${endpoint}`, {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${authToken}` },
    body: formData,
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    const messages = {
      FILE_TOO_LARGE:  'Fichier trop volumineux',
      INVALID_MIME:    'Format de fichier non accepté',
      DANGEROUS_FILE:  'Fichier refusé pour raisons de sécurité',
    };
    throw new Error(messages[err.code] || err.message || `Erreur ${response.status}`);
  }
  return response.json();
}

/**
 * Obtenir une URL signée pour afficher un document sensible.
 * @param {string} kycId     - ID du document KYC (votre base Django)
 * @param {string} authToken - JWT de l'utilisateur
 * @returns {Promise<string>} - URL signée valable 60 secondes
 */
async function getSignedUrl(kycId, authToken) {
  const res = await fetch(`${API_BASE}/api/kyc/${kycId}/view/`, {
    headers: { 'Authorization': `Bearer ${authToken}` }
  });
  if (!res.ok) throw new Error('Impossible d\'obtenir l\'accès au document');
  const data = await res.json();
  return data.signed_url;
}

// ── Exemple d'utilisation dans une page HTML
document.getElementById('avatarInput').addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (!file) return;

  try {
    const result = await uploadFile(file, '/api/users/avatar/', getUserToken());
    // Mettre à jour l'image avatar sur la page
    document.getElementById('avatarImg').src = result.avatar_url;
    showSuccess('Photo de profil mise à jour !');
  } catch (err) {
    showError(err.message);
  }
});

// Afficher un document KYC (iframe temporaire)
async function showKycDocument(kycId) {
  const iframe = document.getElementById('kycViewer');
  try {
    const url = await getSignedUrl(kycId, getUserToken());
    iframe.src = url;
    iframe.style.display = 'block';
    // Cacher l'iframe après 58 secondes (URL expire à 60s)
    setTimeout(() => {
      iframe.src = '';
      iframe.style.display = 'none';
    }, 58000);
  } catch (err) {
    showError('Impossible d\'afficher le document : ' + err.message);
  }
}""",
    caption='JavaScript vanilla — utilitaires génériques réutilisables')

    # ── 23.4 Gestion des erreurs côté client
    h2 = doc.add_heading('23.4 Tableau de gestion des erreurs côté client', level=2)
    style_heading(h2, 2)

    doc.add_paragraph(
        'Voici les erreurs que votre frontend peut recevoir de votre backend Django '
        '(qui les relaie depuis le storage-service) et le message à afficher à l\'utilisateur :'
    )

    add_styled_table(doc,
        headers=['Code erreur', 'HTTP', 'Message utilisateur recommandé', 'Action à faire'],
        rows=[
            ['FILE_TOO_LARGE',         '413', 'Votre fichier est trop volumineux.',     'Afficher la limite (5 MB avatar, 10 MB KYC)'],
            ['INVALID_MIME',           '400', 'Ce format de fichier n\'est pas accepté.', 'Indiquer les formats autorisés'],
            ['DANGEROUS_FILE',         '400', 'Ce fichier ne peut pas être envoyé.',    'Pas de détail supplémentaire côté utilisateur'],
            ['EMPTY_FILE',             '400', 'Le fichier est vide.',                   'Demander de re-sélectionner'],
            ['ACCESS_DENIED',          '403', 'Vous n\'avez pas accès à ce document.',  'Vérifier les droits utilisateur'],
            ['FILE_NOT_FOUND',         '404', 'Ce document n\'existe plus.',             'Nettoyer la référence en base Django'],
            ['SIGNED_URL_EXPIRED',     '403', 'Le lien a expiré. Rafraîchissez la page.','Re-demander une URL signée automatiquement'],
            ['SIGNED_URL_INVALID',     '403', 'Lien invalide.',                         'Logger l\'incident — tentative de falsification'],
            ['INTERNAL_ERROR',         '500', 'Erreur technique. Réessayez.',            'Logger + alerter l\'équipe technique'],
        ],
        col_widths=[3.8, 1.4, 5.5, 5.8]
    )

    # ── 23.5 Checklist d'intégration
    h2 = doc.add_heading('23.5 Checklist d\'intégration pour les développeurs', level=2)
    style_heading(h2, 2)

    checklist_integ = [
        ('Backend (Django)', [
            'Installer django_integration/storage_client.py et configurer settings.py',
            'Ne jamais exposer STORAGE_API_KEY dans le code front-end ou les logs',
            'Stocker file_id en base de données, pas l\'URL (pour les fichiers sensibles)',
            'Retourner les codes d\'erreur machine au front-end pour affichage précis',
            'Implémenter un endpoint /api/kyc/{id}/view/ qui génère l\'URL signée à la demande',
            'Vérifier les droits utilisateur dans Django avant de demander une URL signée',
        ]),
        ('Application Mobile (React Native)', [
            'Valider taille et type côté client avant envoi (UX rapide)',
            'Ne jamais hardcoder la clé API dans le code mobile',
            'Afficher les avatars publics directement via l\'URL CDN (pas de proxy)',
            'Utiliser WebView pour afficher les documents sensibles via URL signée',
            'Gérer l\'expiration de l\'URL signée (60s) — prévoir un bouton "Actualiser"',
            'Tester avec des fichiers volumineux, des formats refusés, et sans réseau',
        ]),
        ('Application Web (React / Vue)', [
            'Valider le type et la taille côté client via File.type et File.size',
            'Afficher une prévisualisation locale avant l\'upload (URL.createObjectURL)',
            'Gérer l\'état loading / error / success avec retour visuel clair',
            'Pour les documents sensibles : iframe temporaire avec timer d\'expiration',
            'Ne pas mettre en cache les URLs signées côté client',
            'Ajouter Content-Security-Policy dans votre HTML pour les iframes KYC',
        ]),
    ]

    for cat_name, items in checklist_integ:
        h3 = doc.add_heading(cat_name, level=3)
        style_heading(h3, 3)
        for item in items:
            p = doc.add_paragraph(style='List Bullet')
            run = p.add_run('☐  ' + item)
            run.font.size = Pt(10.5)

    doc.add_page_break()

    # ── PAGE FINALE
    doc.add_page_break()
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(80)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run('SAAS SENDBID — Storage Service')
    run.font.size = Pt(16)
    run.font.bold = True
    run.font.color.rgb = C_PURPLE

    p2 = doc.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run2 = p2.add_run(f'Documentation générée le {datetime.datetime.now().strftime("%d/%m/%Y à %H:%M")}\nWIB Company — Confidentiel')
    run2.font.size = Pt(10)
    run2.font.color.rgb = C_MID_GREY
    run2.font.italic = True

    add_horizontal_line(doc)

    output_path = r'C:\Users\Albert WIB\sendbid-storage-service\SENDBID_StorageService_Documentation.docx'
    doc.save(output_path)
    print(f'Document généré : {output_path}')
    return output_path


if __name__ == '__main__':
    path = build_document()
    print(f'Taille du fichier : {__import__("os").path.getsize(path) / 1024:.1f} KB')
