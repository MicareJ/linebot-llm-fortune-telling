from rag import rag

# This is the chatbox main application
def main():
    name = input("算命測試中，請輸入您的姓名...")
    date = input("請輸入您的出生年月日(YYYY-MM-DD)...")
    question = input("請輸入您的問題...")

    while   question.lower() != "bye":
        inputprompt = f"姓名: {name}, 出生日期: {date}, 問題: {question}"
        print(f"算命師回應：/n{rag(inputprompt)}") # Call the rag function to perform the analysis

        question = input("請繼續輸入您的問題(或輸入 'bye' 結束)...")

if __name__ == "__main__":
    main()