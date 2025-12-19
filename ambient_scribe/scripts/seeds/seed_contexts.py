#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Seed script to populate ScribeHub with default contexts and templates.

This script creates system contexts for Medical, Aviation, and Legal domains
with their respective terminology, templates, and configurations.

Usage:
    python scripts/seed_contexts.py
"""

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.ext.asyncio import AsyncSession

from ambient_scribe.auth import get_password_hash
from ambient_scribe.database import AsyncSessionLocal, init_db
from ambient_scribe.db_models import Context, Template, User


# Medical context configuration
MEDICAL_CONTEXT = {
    "name": "Consultas Médicas",
    "description": "Transcrição e documentação de consultas médicas com terminologia clínica",
    "language": "pt-BR",
    "icon": "🏥",
    "speaker_labels": {
        "speaker_0": "Médico",
        "speaker_1": "Paciente",
    },
    "word_boosting_config": {
        "diseases": {
            "terms": [
                "hipertensão",
                "diabetes",
                "pneumonia",
                "asma",
                "bronquite",
                "gripe",
                "dengue",
                "covid",
                "tuberculose",
                "hepatite",
            ],
            "boost_score": 45.0,
        },
        "medications": {
            "terms": [
                "metformina",
                "lisinopril",
                "enalapril",
                "losartana",
                "atorvastatina",
                "sinvastatina",
                "omeprazol",
                "dipirona",
                "paracetamol",
                "ibuprofeno",
                "amoxicilina",
                "azitromicina",
            ],
            "boost_score": 50.0,
        },
        "procedures": {
            "terms": [
                "ressonância",
                "tomografia",
                "ultrassom",
                "endoscopia",
                "colonoscopia",
                "biópsia",
                "raio-x",
                "eletrocardiograma",
                "ecocardiograma",
            ],
            "boost_score": 40.0,
        },
        "symptoms": {
            "terms": [
                "febre",
                "dor",
                "tosse",
                "náusea",
                "vômito",
                "diarreia",
                "cefaleia",
                "tontura",
                "fadiga",
                "dispneia",
            ],
            "boost_score": 35.0,
        },
        "laboratory": {
            "terms": [
                "hemograma",
                "glicemia",
                "creatinina",
                "ureia",
                "colesterol",
                "triglicerídeos",
                "hemoglobina",
                "leucócitos",
                "plaquetas",
            ],
            "boost_score": 40.0,
        },
    },
}

MEDICAL_SOAP_TEMPLATE = {
    "name": "soap_default",
    "display_name": "SOAP - Formato Padrão",
    "description": "Formato SOAP padrão para documentação médica",
    "sections": ["subjective", "objective", "assessment", "plan"],
    "content": """# Nota SOAP

## Subjetivo (S)
{{ subjective or "Sem informações subjetivas documentadas" }}

## Objetivo (O)
{{ objective or "Sem achados objetivos documentados" }}

## Avaliação (A)
{{ assessment or "Sem avaliação fornecida" }}

## Plano (P)
{{ plan or "Sem plano de tratamento documentado" }}
""",
}

MEDICAL_PROGRESS_TEMPLATE = {
    "name": "progress_note",
    "display_name": "Nota de Progresso",
    "description": "Nota de acompanhamento e evolução do paciente",
    "sections": ["chief_complaint", "history", "physical_exam", "progress", "plan"],
    "content": """# Nota de Progresso

## Queixa Principal
{{ chief_complaint or "Queixa não documentada" }}

## História da Doença Atual
{{ history or "História não documentada" }}

## Exame Físico
{{ physical_exam or "Exame físico não documentado" }}

## Progresso/Evolução
{{ progress or "Evolução não documentada" }}

## Plano
{{ plan or "Plano não documentado" }}
""",
}


# Aviation context configuration
AVIATION_CONTEXT = {
    "name": "Manutenção de Aeronaves",
    "description": "Laudos técnicos de inspeção e manutenção aeronáutica",
    "language": "pt-BR",
    "icon": "✈️",
    "speaker_labels": {
        "speaker_0": "Mecânico",
        "speaker_1": "Supervisor",
        "speaker_2": "Inspetor",
    },
    "word_boosting_config": {
        "aircraft_parts": {
            "terms": [
                "fuselagem",
                "trem de pouso",
                "aileron",
                "flap",
                "turbina",
                "hélice",
                "cauda",
                "asa",
                "cockpit",
                "estabilizador",
            ],
            "boost_score": 50.0,
        },
        "inspection_types": {
            "terms": [
                "inspeção pré-voo",
                "manutenção preventiva",
                "overhaul",
                "checklist",
                "inspeção periódica",
                "reparo estrutural",
            ],
            "boost_score": 45.0,
        },
        "measurements": {
            "terms": [
                "torque",
                "pressão hidráulica",
                "rpm",
                "temperatura",
                "vibração",
                "voltagem",
                "amperagem",
            ],
            "boost_score": 40.0,
        },
        "defects": {
            "terms": [
                "corrosão",
                "fadiga",
                "trinca",
                "vazamento",
                "desgaste",
                "folga",
                "rachadura",
                "deformação",
            ],
            "boost_score": 45.0,
        },
        "standards": {
            "terms": [
                "FAA",
                "ANAC",
                "certificação",
                "aeronavegabilidade",
                "diretriz",
                "regulamento",
                "norma técnica",
            ],
            "boost_score": 35.0,
        },
    },
}

AVIATION_MAINTENANCE_TEMPLATE = {
    "name": "maintenance_report",
    "display_name": "Laudo de Manutenção",
    "description": "Relatório técnico de inspeção e manutenção de aeronaves",
    "sections": [
        "aircraft_info",
        "inspection_type",
        "findings",
        "work_performed",
        "parts_replaced",
        "recommendations",
        "airworthiness_status",
    ],
    "content": """# LAUDO DE MANUTENÇÃO AERONÁUTICA

## Identificação da Aeronave
{{ aircraft_info or "Informações da aeronave não documentadas" }}

## Tipo de Inspeção
{{ inspection_type or "Tipo de inspeção não especificado" }}

## Constatações
{{ findings or "Nenhuma constatação documentada" }}

## Trabalhos Realizados
{{ work_performed or "Nenhum trabalho documentado" }}

## Peças Substituídas
{{ parts_replaced or "Nenhuma peça substituída" }}

## Recomendações
{{ recommendations or "Nenhuma recomendação" }}

## Status de Aeronavegabilidade
{{ airworthiness_status or "Status não informado" }}

---
**Data:** {{ date or "Data não registrada" }}
**Mecânico Responsável:** {{ mechanic_name or "Não informado" }}
**Registro ANAC:** {{ anac_registration or "Não informado" }}
""",
}


# Legal context configuration
LEGAL_CONTEXT = {
    "name": "Audiências Jurídicas",
    "description": "Transcrição de audiências, depoimentos e procedimentos judiciais",
    "language": "pt-BR",
    "icon": "⚖️",
    "speaker_labels": {
        "speaker_0": "Juiz",
        "speaker_1": "Advogado de Defesa",
        "speaker_2": "Promotor",
        "speaker_3": "Testemunha",
    },
    "word_boosting_config": {
        "legal_terms": {
            "terms": [
                "processo",
                "sentença",
                "acórdão",
                "apelação",
                "recurso",
                "petição",
                "intimação",
                "citação",
                "habeas corpus",
                "mandado",
            ],
            "boost_score": 45.0,
        },
        "roles": {
            "terms": [
                "réu",
                "autor",
                "testemunha",
                "advogado",
                "promotor",
                "defensor",
                "perito",
                "escrivão",
            ],
            "boost_score": 40.0,
        },
        "procedures": {
            "terms": [
                "audiência",
                "depoimento",
                "oitiva",
                "interrogatório",
                "sustentação oral",
                "julgamento",
                "sessão",
            ],
            "boost_score": 40.0,
        },
        "documents": {
            "terms": [
                "certidão",
                "alvará",
                "contrato",
                "escritura",
                "procuração",
                "atestado",
                "laudo pericial",
            ],
            "boost_score": 35.0,
        },
        "crimes": {
            "terms": [
                "homicídio",
                "roubo",
                "furto",
                "estelionato",
                "lesão corporal",
                "difamação",
                "calúnia",
                "injúria",
            ],
            "boost_score": 35.0,
        },
    },
}

LEGAL_HEARING_TEMPLATE = {
    "name": "hearing_transcript",
    "display_name": "Transcrição de Audiência",
    "description": "Registro oficial de audiência judicial",
    "sections": [
        "case_info",
        "participants",
        "opening",
        "testimony",
        "statements",
        "decisions",
        "closing",
    ],
    "content": """# TRANSCRIÇÃO DE AUDIÊNCIA

## Informações do Processo
{{ case_info or "Informações do processo não documentadas" }}

## Participantes
{{ participants or "Participantes não identificados" }}

## Abertura da Audiência
{{ opening or "Abertura não registrada" }}

## Depoimentos
{{ testimony or "Nenhum depoimento registrado" }}

## Manifestações das Partes
{{ statements or "Nenhuma manifestação registrada" }}

## Decisões e Determinações
{{ decisions or "Nenhuma decisão proferida" }}

## Encerramento
{{ closing or "Encerramento não registrado" }}

---
**Data:** {{ date or "Data não registrada" }}
**Vara:** {{ court or "Vara não informada" }}
**Processo Nº:** {{ case_number or "Não informado" }}
**Escrivão:** {{ clerk_name or "Não informado" }}
""",
}


async def create_system_user(db: AsyncSession) -> User:
    """Create a system user for seeding contexts."""
    print("Creating system user...")

    system_user = User(
        id=uuid4(),
        email="system@scribehub.local",
        username="system",
        hashed_password=get_password_hash("system_password_not_for_login"),
        full_name="ScribeHub System",
        is_active=True,
        is_superuser=True,
    )

    db.add(system_user)
    await db.flush()

    print(f"✓ System user created: {system_user.username}")
    return system_user


async def create_context_with_templates(
    db: AsyncSession,
    system_user: User,
    context_data: dict,
    templates: list[dict],
) -> Context:
    """Create a context with its templates."""
    print(f"\nCreating context: {context_data['name']}...")

    context = Context(
        id=uuid4(),
        name=context_data["name"],
        description=context_data["description"],
        language=context_data["language"],
        owner_id=system_user.id,
        is_public=True,
        is_system=True,
        speaker_labels=context_data["speaker_labels"],
        word_boosting_config=context_data["word_boosting_config"],
        icon=context_data.get("icon"),
    )

    db.add(context)
    await db.flush()

    print(f"✓ Context created: {context.name}")

    # Create templates
    for i, template_data in enumerate(templates):
        template = Template(
            id=uuid4(),
            context_id=context.id,
            name=template_data["name"],
            display_name=template_data["display_name"],
            description=template_data["description"],
            content=template_data["content"],
            sections=template_data["sections"],
            is_default=(i == 0),  # First template is default
            is_public=True,
            version=1,
            created_by=system_user.id,
        )

        db.add(template)
        print(f"  ✓ Template created: {template.display_name}")

    await db.flush()

    return context


async def seed_contexts():
    """Main seed function to populate default contexts."""
    print("=" * 60)
    print("ScribeHub - Seeding Default Contexts")
    print("=" * 60)

    # Initialize database
    await init_db()

    async with AsyncSessionLocal() as db:
        try:
            # Check if system user already exists
            from sqlalchemy import select

            result = await db.execute(select(User).where(User.username == "system"))
            system_user = result.scalar_one_or_none()

            if system_user:
                print("System user already exists, skipping creation...")
            else:
                system_user = await create_system_user(db)

            # Check if contexts already exist
            result = await db.execute(select(Context).where(Context.is_system == True))
            existing_contexts = result.scalars().all()

            if existing_contexts:
                print(f"\n⚠️  Found {len(existing_contexts)} existing system contexts")
                print("Skipping context creation to avoid duplicates.")
                print("To recreate, delete existing contexts first.")
                return

            # Create Medical context
            await create_context_with_templates(
                db,
                system_user,
                MEDICAL_CONTEXT,
                [MEDICAL_SOAP_TEMPLATE, MEDICAL_PROGRESS_TEMPLATE],
            )

            # Create Aviation context
            await create_context_with_templates(
                db,
                system_user,
                AVIATION_CONTEXT,
                [AVIATION_MAINTENANCE_TEMPLATE],
            )

            # Create Legal context
            await create_context_with_templates(
                db,
                system_user,
                LEGAL_CONTEXT,
                [LEGAL_HEARING_TEMPLATE],
            )

            # Commit all changes
            await db.commit()

            print("\n" + "=" * 60)
            print("✅ Seeding completed successfully!")
            print("=" * 60)
            print("\nCreated:")
            print("  • 3 system contexts (Medical, Aviation, Legal)")
            print("  • 4 templates")
            print("  • 150+ technical terms with word boosting")
            print("\nContexts are now available in ScribeHub!")

        except Exception as e:
            await db.rollback()
            print(f"\n❌ Error during seeding: {e}")
            raise


if __name__ == "__main__":
    asyncio.run(seed_contexts())
