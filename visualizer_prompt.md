# Visualizer Implementation Task

Based on `schedule_result.csv` and the original `day_ahead_data.csv`, implement a visualization script `visualizer.py`.

## Requirements:
1. **Library:** Use `matplotlib` and `pandas`.
2. **Functionality:** 
   - Load the CSV files.
   - Create a single figure with subplots (or separate figures if clearer).
   - Plot the "Duck Curve" (Base Load + PV + WT).
   - Plot Battery SOC evolution over the 24 hours.
   - Plot the Power Schedule (Grid Buy/Sell, ESS Charge/Discharge).
3. **Style:** Use a clean, professional style (grid, labels, legend, clear colors). Use Chinese labels if possible for the legend.
4. **Output:** The script should generate and save a PDF or PNG file named `schedule_visualization.png`.
5. **Code Quality:** Production-grade code with detailed **Chinese comments**.
6. **Testing:** The script must run successfully standalone `python visualizer.py` and produce the image.
7. **Self-Correction:** Install `matplotlib` if missing in the `.venv`.

Please write `visualizer.py`, test it, and confirm the image file is created.