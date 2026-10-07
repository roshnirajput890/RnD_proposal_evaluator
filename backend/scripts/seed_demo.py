#!/usr/bin/env python3
"""
Seed demo evaluations for portfolio demonstration.

Creates 7 realistic sample evaluations with is_demo=0, covering:
  - Varied topics and scores (2.0 to 4.4)
  - Different score bands (Recommend, Revise, Not Recommended)
  - Dates distributed across Sept 28 - Oct 6, 2026 (5 specific dates)
  - One with financial arithmetic mismatch
  - 2-3 with human reviewer feedback

Idempotent: deletes existing demo records before inserting new ones.

Usage:
  python scripts/seed_demo.py
"""
import sqlite3
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "evaluations.db"


# Sample evaluation templates
DEMO_EVALUATIONS = [
    {
        "filename": "solar_water_purification.pdf",
        "title": "Solar-Powered Water Purification for Rural Communities",
        "main_idea": "A low-cost, solar-powered water purification system using UV-C sterilization and activated carbon filtration, designed for off-grid rural communities in developing regions.",
        "problem": "Over 2 billion people lack access to safe drinking water. Existing purification systems require electricity or expensive consumables, making them impractical for remote areas.",
        "solution": "Integrated solar panel and battery system powering UV-C LEDs and a multi-stage filtration unit. Processes 50L/hour at <$0.02 per liter operational cost.",
        "page_count": 18,
        "char_count": 42300,
        "scores": {"novelty": 3, "technical": 4, "financial": 4, "impact": 5},
        "overall": 4.15,
        "band": "Recommend",
        "coordinator": {
            "overall_summary": "Strong proposal with clear social impact and technically sound approach. Solar UV-C purification is proven technology applied innovatively to rural settings. Financial projections are realistic with detailed cost breakdown. High implementation potential.",
            "preliminary_recommendation": "Recommend",
            "coordinator_confidence": "high",
            "strengths": [
                "Exceptional social impact potential — addresses critical need for 2B+ people",
                "Technically feasible with proven UV-C and filtration components",
                "Cost-effective at $0.02/L operational cost vs $0.15/L for alternatives",
                "Detailed pilot study plan with 3 test sites in Kenya and Bangladesh"
            ],
            "risks": [
                "Supply chain dependency on solar panels — consider local sourcing",
                "User training requirements for maintenance not fully addressed"
            ],
            "key_questions": []
        },
        "days_ago": 8,  # Sept 28, 2026
        "reviewed": True,
        "reviewer_decision": "Approve",
        "reviewer_notes": "Excellent proposal. Social impact is compelling and technical approach is sound. Recommend full funding.",
        "reviewer_overrides": {}
    },
    {
        "filename": "federated_learning_hospitals.pdf",
        "title": "Privacy-Preserving Federated Learning for Hospital Networks",
        "main_idea": "A federated learning framework enabling multiple hospitals to collaboratively train diagnostic AI models while keeping patient data local, using differential privacy and secure aggregation.",
        "problem": "Medical AI requires large datasets, but privacy regulations (HIPAA, GDPR) prevent hospitals from sharing patient data. Siloed datasets limit model quality.",
        "solution": "Federated learning system where models train locally at each hospital, only encrypted model updates are shared. Achieves 94% accuracy vs 96% for centralized training.",
        "page_count": 28,
        "char_count": 68500,
        "scores": {"novelty": 4, "technical": 5, "financial": 3, "impact": 4},
        "overall": 4.05,
        "band": "Recommend",
        "coordinator": {
            "overall_summary": "Innovative approach to a critical healthcare AI problem. Technical implementation is sophisticated with strong privacy guarantees. Minor concerns about deployment costs and hospital adoption barriers. Overall a solid research proposal with significant potential.",
            "preliminary_recommendation": "Recommend",
            "coordinator_confidence": "high",
            "strengths": [
                "Addresses critical privacy barrier in medical AI",
                "Technically rigorous with differential privacy (ε=1.5) and secure aggregation",
                "Validation plan includes 8 hospital partners across 3 countries",
                "Minimal accuracy loss (2%) vs centralized training"
            ],
            "risks": [
                "High initial deployment costs ($45K per hospital) may limit adoption",
                "Requires significant IT infrastructure upgrades at partner hospitals",
                "Regulatory approval timeline uncertain (6-12 months estimated)"
            ],
            "key_questions": []
        },
        "days_ago": 8,  # Sept 28, 2026
        "reviewed": False,
        "reviewer_decision": None,
        "reviewer_notes": None,
        "reviewer_overrides": {}
    },
    {
        "filename": "soil_sensor_network.pdf",
        "title": "Low-Cost IoT Soil Moisture Sensor Network for Precision Agriculture",
        "main_idea": "Network of $8 wireless soil sensors using LoRaWAN connectivity, providing real-time moisture and pH data to farmers via mobile app for optimized irrigation.",
        "problem": "Smallholder farmers lack affordable tools for precision irrigation. Over-watering wastes resources; under-watering reduces yields. Existing sensors cost $200+ each.",
        "solution": "Custom PCB design with capacitive moisture sensor and pH probe, ESP32 microcontroller, LoRaWAN radio. Solar-powered with 2-year battery life. Cloud dashboard and SMS alerts.",
        "page_count": 15,
        "char_count": 35200,
        "scores": {"novelty": 2, "technical": 3, "financial": 3, "impact": 4},
        "overall": 3.05,
        "band": "Revise and Resubmit",
        "coordinator": {
            "overall_summary": "Practical proposal addressing real agricultural need. Technical approach is sound but not particularly novel—similar commercial solutions exist. Financial projections lack detail on scaling costs. Impact potential is good for smallholder farmers. Needs stronger differentiation from existing products.",
            "preliminary_recommendation": "Revise and Resubmit",
            "coordinator_confidence": "medium",
            "strengths": [
                "Addresses genuine need for affordable precision agriculture tools",
                "Cost target of $8/sensor is significantly below market alternatives",
                "LoRaWAN provides good range (5km) for rural deployment"
            ],
            "risks": [
                "Limited novelty—capacitive sensors and LoRaWAN are standard technology",
                "Market analysis incomplete—existing $50-100 solutions not addressed",
                "Calibration accuracy (±3% moisture) may be insufficient for some crops",
                "Distribution and support model for remote farmers unclear"
            ],
            "key_questions": [
                "How does this differentiate from commercial offerings like METER Group sensors?",
                "What is the plan for calibration and maintenance in remote locations?",
                "Can the proposed cost be sustained at scale with component supply chains?"
            ]
        },
        "days_ago": 6,  # Sept 30, 2026
        "reviewed": True,
        "reviewer_decision": "Revise",
        "reviewer_notes": "Good technical foundation but needs stronger market differentiation. Address calibration concerns and provide more detailed cost analysis at scale before resubmission.",
        "reviewer_overrides": {}
    },
    {
        "filename": "quantum_safe_encryption.pdf",
        "title": "Post-Quantum Cryptographic Module for Legacy Financial Systems",
        "main_idea": "Drop-in cryptographic library implementing NIST-standardized post-quantum algorithms (CRYSTALS-Kyber, Dilithium) for banks to upgrade aging transaction systems against quantum threats.",
        "problem": "Current RSA/ECC encryption will be broken by quantum computers within 10-15 years. Banks have legacy COBOL systems that cannot be replaced but must be quantum-resistant.",
        "solution": "C library with Python/Java bindings, API-compatible with OpenSSL. Implements hybrid classical+PQC mode for gradual transition. 40% performance overhead vs RSA.",
        "page_count": 34,
        "char_count": 82100,
        "scores": {"novelty": 4, "technical": 5, "financial": 2, "impact": 3},
        "overall": 3.50,
        "band": "Revise and Resubmit",
        "coordinator": {
            "overall_summary": "Technically excellent implementation of post-quantum cryptography with strong engineering approach. However, significant concerns about financial viability and market timing. Budget shows arithmetic mismatch ($380K requested but justification totals $290K). Impact is moderate as quantum threat timeline is uncertain.",
            "preliminary_recommendation": "Revise and Resubmit",
            "coordinator_confidence": "medium",
            "strengths": [
                "Implements NIST-approved PQC standards (Kyber, Dilithium)",
                "Hybrid mode enables gradual migration without breaking existing systems",
                "Performance overhead (40%) is acceptable for financial transactions",
                "Strong team with cryptography and banking system expertise"
            ],
            "risks": [
                "Financial arithmetic mismatch: $380K requested but line items total $290K",
                "Market timing unclear—quantum threat is 10-15 years out, banks may delay adoption",
                "Adoption barriers: banks are risk-averse and slow to change core systems",
                "No pilot customers identified—validation plan lacks real-world testing"
            ],
            "key_questions": [
                "Please reconcile budget discrepancy between total ($380K) and justification ($290K)",
                "Which banks have committed to pilot testing?",
                "What is the go-to-market strategy given long quantum timeline?"
            ]
        },
        "days_ago": 6,  # Sept 30, 2026
        "reviewed": True,
        "reviewer_decision": "Revise",
        "reviewer_notes": "Strong technical work but budget discrepancy must be resolved. Need concrete pilot partners before approval. Clarify market strategy.",
        "reviewer_overrides": {"financial": {"score": 2, "comment": "Budget arithmetic mismatch requires correction before approval"}}
    },
    {
        "filename": "ai_crop_yield_forecasting.pdf",
        "title": "Multi-Modal AI for Crop Yield Forecasting Using Satellite Imagery",
        "main_idea": "Deep learning model combining satellite RGB/NIR imagery, weather data, and soil composition to predict crop yields 6 weeks before harvest with 89% accuracy.",
        "problem": "Farmers and commodity traders lack accurate advance yield predictions. Current methods rely on manual field surveys or simple statistical models with <70% accuracy.",
        "solution": "Convolutional neural network trained on 5 years of Sentinel-2 imagery, weather APIs, and ground truth yield data from 12,000 farms. Web dashboard for farmers and insurers.",
        "page_count": 22,
        "char_count": 51800,
        "scores": {"novelty": 3, "technical": 4, "financial": 4, "impact": 4},
        "overall": 3.80,
        "band": "Recommend",
        "coordinator": {
            "overall_summary": "Well-executed AI application to agriculture with strong validation results. Technical approach is solid, combining multiple data sources effectively. Financial projections are reasonable with clear revenue model. Good commercialization potential.",
            "preliminary_recommendation": "Recommend",
            "coordinator_confidence": "high",
            "strengths": [
                "89% accuracy significantly exceeds current 70% baseline",
                "Validated on real farms across 3 continents (US, Brazil, India)",
                "Multiple revenue streams: farmer subscriptions, insurance APIs, commodity traders",
                "Strong technical foundation with proven CNN architecture"
            ],
            "risks": [
                "Accuracy may degrade for crops not in training set",
                "Cloud cover can disrupt satellite imagery in monsoon regions",
                "Competition from established agtech companies (Climate FieldView, FarmLogs)"
            ],
            "key_questions": []
        },
        "days_ago": 4,  # Oct 2, 2026
        "reviewed": False,
        "reviewer_decision": None,
        "reviewer_notes": None,
        "reviewer_overrides": {}
    },
    {
        "filename": "wearable_ecg_monitor.pdf",
        "title": "Continuous Wearable ECG Monitor with Atrial Fibrillation Detection",
        "main_idea": "Patch-style 7-day continuous ECG monitor with onboard ML processor detecting atrial fibrillation in real-time. Costs $45 vs $300 for Holter monitors.",
        "problem": "Atrial fibrillation (AFib) affects 33M people globally but is often asymptomatic. Traditional Holter monitors are expensive and uncomfortable, limiting screening adoption.",
        "solution": "Disposable adhesive patch with 3-lead ECG, STM32 MCU running TinyML AFib classifier (97% sensitivity), Bluetooth sync to smartphone. 7-day battery, IP67 waterproof.",
        "page_count": 20,
        "char_count": 47600,
        "scores": {"novelty": 3, "technical": 3, "financial": 3, "impact": 4},
        "overall": 3.30,
        "band": "Revise and Resubmit",
        "coordinator": {
            "overall_summary": "Practical medical device addressing a real screening gap. Technical design is competent but faces significant regulatory and competitive hurdles. Financial model underestimates FDA approval costs ($150K budgeted vs typical $500K+ for Class II devices). Market is crowded with Apple Watch and KardiaMobile.",
            "preliminary_recommendation": "Revise and Resubmit",
            "coordinator_confidence": "medium",
            "strengths": [
                "Addresses important AFib screening need (33M affected globally)",
                "Cost advantage over traditional Holter monitors ($45 vs $300)",
                "Good technical specs: 97% AFib sensitivity, 7-day battery, waterproof"
            ],
            "risks": [
                "FDA Class II approval timeline and cost significantly underestimated",
                "Strong competition from Apple Watch ECG and AliveCor KardiaMobile",
                "Clinical validation study (n=50) is too small for regulatory submission",
                "Reimbursement strategy unclear—will insurers cover this vs established devices?"
            ],
            "key_questions": [
                "How will you compete with Apple Watch Series 4+ which already has FDA clearance?",
                "What is realistic FDA approval budget and timeline?",
                "What clinical trial size is needed for regulatory submission?"
            ]
        },
        "days_ago": 2,  # Oct 4, 2026
        "reviewed": False,
        "reviewer_decision": None,
        "reviewer_notes": None,
        "reviewer_overrides": {}
    },
    {
        "filename": "battery_recycling_process.pdf",
        "title": "Hydrometallurgical Lithium-Ion Battery Recycling at 95% Recovery Rate",
        "main_idea": "Novel acid-leaching process recovering 95% of lithium, cobalt, and nickel from spent EV batteries using sulfuric acid at 80°C. 50% lower energy than pyrometallurgy.",
        "problem": "Only 5% of lithium-ion batteries are currently recycled. Pyrometallurgy is energy-intensive and loses lithium. Landfilling wastes valuable metals and creates environmental hazards.",
        "solution": "Three-stage leaching with H₂SO₄ + H₂O₂, selective precipitation of cobalt/nickel/lithium, purification to battery-grade carbonates. Pilot plant processes 100kg/day.",
        "page_count": 26,
        "char_count": 63400,
        "scores": {"novelty": 2, "technical": 3, "financial": 2, "impact": 3},
        "overall": 2.50,
        "band": "Not Recommended",
        "coordinator": {
            "overall_summary": "Incremental improvement to existing hydrometallurgical recycling methods. While 95% recovery is good, the approach is not significantly novel—sulfuric acid leaching is standard in the industry. Financial projections are weak with high capital costs ($2.8M pilot plant) and unclear competitive advantage. Market analysis lacks depth on existing recyclers (Li-Cycle, Redwood Materials).",
            "preliminary_recommendation": "Not Recommended",
            "coordinator_confidence": "high",
            "strengths": [
                "95% metal recovery rate is competitive with industry leaders",
                "Energy savings (50% vs pyrometallurgy) reduces operating costs",
                "Pilot plant demonstrates technical feasibility"
            ],
            "risks": [
                "Limited novelty—sulfuric acid leaching is standard practice",
                "High capital costs ($2.8M) for 100kg/day pilot scale",
                "Strong competition from well-funded players (Li-Cycle $4.4B valuation, Redwood Materials $3.7B)",
                "No IP protection—process is not patentable as described",
                "Economics unclear—recovery cost not compared to virgin material pricing",
                "Scaling analysis missing—path from 100kg/day pilot to commercial tonnage"
            ],
            "key_questions": [
                "What is your competitive advantage vs Li-Cycle and Redwood Materials?",
                "Have you filed patents? If not, what protects this business?",
                "What is the break-even scale and timeline to reach it?"
            ]
        },
        "days_ago": 0,  # Oct 6, 2026
        "reviewed": True,
        "reviewer_decision": "Reject",
        "reviewer_notes": "Insufficient novelty and weak competitive positioning. Existing well-funded companies already operate at scale with similar technology. No clear IP protection or differentiation.",
        "reviewer_overrides": {}
    }
]


def create_demo_record(conn, eval_data, days_ago):
    """Create a single demo evaluation record."""
    record_id = str(uuid.uuid4())
    created_at = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    
    # Build result_json matching real structure
    result_json = {
        "analysis": {
            "title_or_topic": eval_data["title"],
            "main_idea_summary": eval_data["main_idea"],
            "main_problem": eval_data["problem"],
            "proposed_solution": eval_data["solution"],
            "truncated": False,
            "_status": "completed"
        },
        "novelty": {
            "score": eval_data["scores"]["novelty"],
            "score_justification": f"Novelty score {eval_data['scores']['novelty']}/5",
            "summary": "Novelty evaluation completed",
            "status": "completed",
            "external_evidence_used": False
        },
        "technical": {
            "score": eval_data["scores"]["technical"],
            "score_justification": f"Technical score {eval_data['scores']['technical']}/5",
            "summary": "Technical evaluation completed",
            "status": "completed"
        },
        "financial": {
            "score": eval_data["scores"]["financial"],
            "score_justification": f"Financial score {eval_data['scores']['financial']}/5",
            "summary": "Financial evaluation completed",
            "status": "completed"
        },
        "impact": {
            "score": eval_data["scores"]["impact"],
            "score_justification": f"Impact score {eval_data['scores']['impact']}/5",
            "summary": "Impact evaluation completed",
            "status": "completed"
        },
        "scoring": {
            "overall_score": eval_data["overall"],
            "score_band": eval_data["band"],
            "novelty_score": eval_data["scores"]["novelty"],
            "technical_score": eval_data["scores"]["technical"],
            "financial_score": eval_data["scores"]["financial"],
            "impact_score": eval_data["scores"]["impact"]
        },
        "coordinator": eval_data["coordinator"],
        "_agent_statuses": {
            "general_analysis": "completed",
            "novelty_agent": "completed",
            "technical_agent": "completed",
            "financial_agent": "completed",
            "impact_agent": "completed",
            "coordinator": "completed"
        },
        "truncation_applied": False
    }
    
    # Reviewer fields
    reviewer_overrides_json = json.dumps(eval_data["reviewer_overrides"]) if eval_data["reviewer_overrides"] else None
    reviewer_updated_at = created_at if eval_data["reviewed"] else None
    
    conn.execute("""
        INSERT INTO evaluations (
            id, filename, title_or_topic, main_idea, main_problem,
            proposed_solution, page_count, char_count, model_used,
            status, truncated, result_json, created_at,
            coordinator_summary, preliminary_recommendation, recommendation_reasoning,
            novelty_score, technical_score, financial_score, impact_score,
            overall_score, score_band,
            reviewer_overrides, reviewer_final_decision, reviewer_notes, reviewer_updated_at,
            is_demo
        ) VALUES (
            ?,?,?,?,?,?,?,?,?,'completed',0,?,?,
            ?,?,?,
            ?,?,?,?,?,?,
            ?,?,?,?,
            0
        )
    """, (
        record_id,
        eval_data["filename"],
        eval_data["title"],
        eval_data["main_idea"],
        eval_data["problem"],
        eval_data["solution"],
        eval_data["page_count"],
        eval_data["char_count"],
        "gemma3:4b",
        json.dumps(result_json, ensure_ascii=False),
        created_at,
        json.dumps(eval_data["coordinator"], ensure_ascii=False),
        eval_data["coordinator"]["preliminary_recommendation"],
        None,  # recommendation_reasoning
        eval_data["scores"]["novelty"],
        eval_data["scores"]["technical"],
        eval_data["scores"]["financial"],
        eval_data["scores"]["impact"],
        eval_data["overall"],
        eval_data["band"],
        reviewer_overrides_json,
        eval_data["reviewer_decision"],
        eval_data["reviewer_notes"],
        reviewer_updated_at
    ))


def seed_demo_evaluations():
    """Main seeding function."""
    if not DB_PATH.exists():
        print(f"ERROR: Database not found at {DB_PATH}")
        return
    
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    # Check if is_demo column exists
    cursor.execute("PRAGMA table_info(evaluations)")
    columns = [row[1] for row in cursor.fetchall()]
    if "is_demo" not in columns:
        print("ERROR: is_demo column does not exist. Run migration first:")
        print("  python scripts/migrate_add_is_demo.py")
        conn.close()
        return
    
    # Delete existing demo records (idempotent)
    # Delete by filename to ensure no duplicates
    print(f"Removing existing demo evaluation records...")
    for eval_data in DEMO_EVALUATIONS:
        cursor.execute("DELETE FROM evaluations WHERE filename = ?", (eval_data["filename"],))
    conn.commit()
    
    # Insert new demo records (now marked as is_demo=0, indistinguishable from real records)
    print(f"\nInserting {len(DEMO_EVALUATIONS)} demo evaluations...")
    for i, eval_data in enumerate(DEMO_EVALUATIONS, 1):
        create_demo_record(conn, eval_data, eval_data["days_ago"])
        print(f"  {i}. {eval_data['filename']:40} | Score: {eval_data['overall']:.2f} | {eval_data['band']}")
    
    conn.commit()
    
    # Verify
    cursor.execute("SELECT COUNT(*) FROM evaluations WHERE is_demo = 1")
    old_demo_count = cursor.fetchone()[0]
    
    # Count by filename
    placeholders = ','.join('?' * len(DEMO_EVALUATIONS))
    filenames = [e["filename"] for e in DEMO_EVALUATIONS]
    cursor.execute(f"SELECT COUNT(*) FROM evaluations WHERE filename IN ({placeholders})", filenames)
    total_demo_files = cursor.fetchone()[0]
    
    print(f"\n{'='*80}")
    print(f"✓ Demo seeding complete!")
    print(f"  Demo evaluation records (7 filenames): {total_demo_files}")
    if old_demo_count > 0:
        print(f"  Note: {old_demo_count} old is_demo=1 flagged records remain (run cleanup if needed)")
    print(f"{'='*80}")
    
    conn.close()


if __name__ == "__main__":
    seed_demo_evaluations()
