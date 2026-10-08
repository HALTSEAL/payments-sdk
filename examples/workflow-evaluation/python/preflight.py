"""Check workflow input and adapter configuration. This does not run an engine."""
import argparse
import json
from pathlib import Path
from contract import load_workflow
from hooks import load_adapter

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workflow", type=Path, required=True)
    p.add_argument("--adapter", type=Path, default=Path(__file__).with_name("customer_adapter.py"))
    args = p.parse_args()
    try:
        load_workflow(args.workflow)
        adapter = load_adapter(args.adapter.resolve())
        print(json.dumps({"status": "READY_TO_EVALUATE", "adapter_kind": adapter.adapter_kind,
                          "engine_executed": False, "production": "NO_GO"}))
    except (ValueError, RuntimeError, AttributeError, OSError) as error:
        print(json.dumps({"status": "INCOMPLETE", "reason": str(error), "engine_executed": False}))
        raise SystemExit(2)
