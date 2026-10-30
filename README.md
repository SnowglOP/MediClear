# MediClear

MediClear is a web app that turns confusing medical lab reports and doctor notes into simple plain English. When you get blood test results back from a lab, the sheet is usually full of medical terms and numbers without telling you what to do next. MediClear reads your report, calculates how far your numbers are from the normal range, gives you daily food and movement swaps, and tracks your daily streak on a calendar until your next checkup.

## What You Need Before Starting

1. Python installed on your computer.
2. A free Gemini API key from Google AI Studio.
3. A medical lab report PDF file or text from a doctor note.

## How to Set Up and Run the App

1. Put `app.py` and `requirements.txt` in the same folder.
2. Create a file named `.env` in that same folder and put your API key inside it like this:
   `GEMINI_API_KEY=your_api_key_here`
3. Open your terminal in VS Code and install the required packages from `requirements.txt`.
4. Start the app by running:
   `python -m streamlit run app.py`

## How to Use MediClear

### 1. Upload or Paste Your Lab Report
Open the upload box at the top of the page. You can upload a PDF or text file from labs like Quest Diagnostics or Labcorp, or paste your lab numbers into the text box. Click **Extract, Save & Generate Action Plan**. Within about three seconds, the app reads your numbers and saves your report into a local database file (`mediclear_history.db`) on your computer.

### 2. Read or Listen to Your Results
On the left side under **What Your Doctor's Sheet Says**, you will see each lab marker, its normal reference range, a visual bar, and the exact percentage your number is above or below the normal limit. If your report includes cholesterol or blood sugar markers, the app also calculates heart and glucose ratios such as the LDL to HDL ratio, the Triglyceride to HDL ratio, and Estimated Average Glucose.

On the right side under **Easy to Read Plain English**, you will see a simple explanation of what every lab test means for your body. You can also click the **Generate & Play Audio Summary Aloud** button to open an audio player that reads your summary out loud.

### 3. Follow Your Daily Action Plan
For every lab marker that is flagged as High or Low, MediClear creates an Action Plan card with two daily changes:
* **Swap 1 (Daily Nutrition Swap):** Shows what food to avoid (`Instead Of`) and what whole food to eat (`Try This`).
* **Swap 2 (Movement & Lifestyle Habit):** Shows a sedentary habit to avoid and a daily movement or lifestyle habit to try instead.

If you have lab markers that are already in the **Optimal** range, click the Optimal dropdown below the action cards to see what healthy habits you should continue doing.

### 4. Track Your Rolling 7 Day Calendar Streak
Under the **Rolling 7 Day Tracker**, the app automatically detects today's real date and shows the last 7 calendar days. Each day you complete your swaps, check the box under that date.
* Checking boxes updates the **30 Day Target Graph** live to show how your weekly consistency closes the gap between your current lab number and the healthy normal boundary.
* Every date you check off is saved automatically to your database. You can open the **View Complete Past Habit Log History** dropdown to see all the past dates you completed or log an older date on the calendar.

### 5. Download Your Doctor Summary and Manage Past Reports
At the bottom of the page, MediClear creates a **30 Second Doctor Visit Summary** showing your lab math, your swaps, and all your logged dates. Click **Download Doctor Summary (.txt)** to save it for your next checkup.

To view old checkups, click the **Past Extracted PDFs & History** tab at the top (or use the list in the left sidebar). From there, you can switch between past PDFs in one click, inspect the raw extracted text, delete a single report, or wipe your entire saved history.

#### Made with the assistance of AI
