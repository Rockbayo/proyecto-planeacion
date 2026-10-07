import pandas as pd
import sys

def analyze_excel(filepath):
    print(f"Analyzing {filepath}")
    try:
        df = pd.read_excel(filepath, sheet_name=0)
        pd.set_option('display.max_columns', None)
        print(df.head(20))
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    analyze_excel("TEST_CUSHION.xlsx")

