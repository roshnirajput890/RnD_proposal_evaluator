"""End-to-end test of full evaluation pipeline with all agents."""
import sys, time, logging

# Configure logging to see TIMING logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)

def main():
    from app.services.orchestrator import run_full_evaluation
    
    # Use a simple test proposal text (876 chars - matches the "small" test mentioned)
    proposal_text = """
QUANTUM SENSING FOR ENVIRONMENTAL MONITORING

Problem Statement:
Current environmental monitoring systems lack the precision needed for early detection 
of pollution and climate change indicators. Traditional sensors have limited sensitivity 
and require frequent calibration.

Proposed Solution:
We propose to develop a quantum-enhanced sensing network using nitrogen-vacancy (NV) 
centers in diamond for ultra-sensitive detection of temperature, magnetic fields, and 
chemical signatures. This technology will enable detection of environmental changes 
at unprecedented resolution.

Technical Approach:
Our team will fabricate diamond-based sensors with optimized NV center density, develop
machine learning algorithms for signal processing, and deploy a prototype network across
three test sites. The project builds on our previous work in quantum sensing published
in Nature Photonics 2023.

Budget:
Personnel (2 postdocs, 1 PhD student): $300,000
Equipment (diamond fabrication, optical setup): $150,000  
Travel and materials: $50,000
Total: $500,000

Expected Impact:
This system will provide early warning for environmental hazards, support climate research
with precise measurements, and demonstrate practical quantum technology deployment.""".strip()
    
    print(f"Using test proposal: {len(proposal_text)} characters\n{'='*70}\nRUNNING FULL EVALUATION PIPELINE\n{'='*70}\n")
    
    t_start = time.perf_counter()
    
    try:
        result = run_full_evaluation(
            proposal_text=proposal_text, filename="test_proposal.txt", model=None, timeout=None
        )
        
        t_total = time.perf_counter() - t_start
        
        print(f"\n{'='*70}\nPIPELINE COMPLETED\n{'='*70}\nTotal time: {t_total:.1f}s\n")
        
        scoring = result.get("scoring", {})
        print("SCORE BREAKDOWN:")
        print(f"  Novelty:    {scoring.get('novelty_score', 'n/a')}")
        print(f"  Technical:  {scoring.get('technical_score', 'n/a')}")
        print(f"  Financial:  {scoring.get('financial_score', 'n/a')}")
        print(f"  Impact:     {scoring.get('impact_score', 'n/a')}")
        print(f"  Overall:    {scoring.get('overall_score', 'n/a'):.2f}" if scoring.get('overall_score') else "  Overall:    n/a")
        print(f"  Band:       {scoring.get('score_band', 'n/a')}")
        
        statuses = result.get("_agent_statuses", {})
        print("\nAGENT STATUSES:")
        for agent, status in statuses.items():
            symbol = "✓" if status == "completed" else "✗"
            print(f"  {symbol} {agent}: {status}")
        
        if result.get("coordinator"):
            print(f"\n✓ Coordinator: {result['coordinator'].get('preliminary_recommendation', 'n/a')}")
        else:
            print(f"\n✗ Coordinator failed: {result.get('coordinator_error', 'unknown')}")
        
        print(f"\n{'='*70}")
        
    except Exception as e:
        print(f"\n✗ PIPELINE FAILED: {e}")
        import traceback; traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
