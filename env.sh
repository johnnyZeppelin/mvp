pip install pyyaml ruff mypy pytest
# (Optional) pip install hypothesis  # only if you want property tests to actually run

# Initialize layout & stubs from the Charter
python tools/scaffold.py --init
python tools/scaffold.py --from-charter

# Create a plan (task DAG)
python planner/planner.py


# Execute the plan end-to-end
python tools/orchestrator.py --run

# If you want the full static→dynamic pipeline in one go, you can also run:
# python tools/oracle.py --all
# python tools/oracle.py --update-apis
# which mirrors what the orchestrator does around tests and freezing.



