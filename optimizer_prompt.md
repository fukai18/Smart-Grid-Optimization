# Optimizer Implementation Task

Based on `PRD.md` and the existing `day_ahead_data.csv`, implement the core optimization engine in `optimizer.py`.

## Requirements:
1. **Library:** Use `cvxpy` to formulate the Mixed-Integer Linear Programming (MILP) problem. You can use the default open-source solver (e.g., CBC or GLPK, or whatever cvxpy defaults to that supports MILP, like ECOS_BB or SCIP).
2. **Data Loading:** Read `day_ahead_data.csv` using `pandas`.
3. **Variables:** 
   - Continuous variables for: PV used, WT used, Grid buy, Grid sell, ESS charge, ESS discharge, ESS State of Charge (SOC), Load curtailed (DR).
   - Boolean (0-1) variables for mutually exclusive states:
     - Buy vs. Sell from/to grid (cannot do both simultaneously).
     - ESS Charge vs. Discharge (cannot do both simultaneously).
4. **Constraints:** Formulate the constraints strictly according to the math model in `PRD.md` (power balance, capacity limits, SOC tracking, DR limits).
5. **Objective:** Minimize the total 24-hour daily operation cost.
6. **Code Quality:** Production-grade code with detailed **Chinese comments**.
7. **Testing:** The script must run successfully standalone `python optimizer.py`, print the optimal total cost, and ideally save the scheduled 24-hour result to `schedule_result.csv`.
8. **Self-Correction:** If you encounter `ModuleNotFoundError` or solver errors, install necessary packages (like `cvxpy`, `scipy`) in your `.venv` and debug the formulation. Fix any errors up to 3 times before stopping.

Please write `optimizer.py`, test it in the background terminal, and confirm the result.