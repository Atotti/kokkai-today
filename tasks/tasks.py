import os
import requests
from janome.tokenizer import Tokenizer
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
from datetime import datetime
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import execute_values

# 環境変数を読み込み
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

def fetch_speeches(date, start_record=1, maximum_records=100):
    base_url = "https://kokkai.ndl.go.jp/api/speech"
    speeches = []
    while True:
        params = {
            "from": date,
            "until": date,
            "startRecord": start_record,
            "maximumRecords": maximum_records,
            "recordPacking": "json"
        }
        response = requests.get(base_url, params=params)
        if response.status_code == 200:
            data = response.json()
            if "speechRecord" in data:
                speeches.extend(data['speechRecord'])
                start_record += maximum_records
                if len(data['speechRecord']) < maximum_records:
                    break
            else:
                break
        else:
            print(f"Failed to fetch data for {date}")
            break
    return speeches

def parse_text(text):
    tokenizer = Tokenizer()
    words = []
    temp_word = ""

    for token in tokenizer.tokenize(text):
        # 名詞であれば一時的に保存し、次の名詞に連結
        if token.part_of_speech.startswith("名詞"):
            temp_word += token.surface
        else:
            # 名詞の連続が終わった場合、保存してリセット
            if temp_word:
                words.append(temp_word)
                temp_word = ""
    
    # 最後の名詞の連続を処理
    if temp_word:
        words.append(temp_word)

    # 出現回数をカウントして返す
    return Counter(words)

def save_to_postgres(date, word_counts):
    # データベースに接続
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    # 各単語の出現回数を挿入または更新
    for word, count in word_counts.items():
        cursor.execute("""
            INSERT INTO word_counts (date, word, count)
            VALUES (%s, %s, %s)
            ON CONFLICT (date, word)
            DO UPDATE SET count = word_counts.count + EXCLUDED.count
        """, (date, word, count))
    
    # コミットして接続を閉じる
    conn.commit()
    cursor.close()
    conn.close()

def process_speeches(date):
    speeches = fetch_speeches(date)
    all_word_counts = Counter()
    
    with ThreadPoolExecutor() as executor:
        results = executor.map(parse_text, [speech['speech'] for speech in speeches])
        for word_count in results:
            all_word_counts.update(word_count)
    
    save_to_postgres(date, all_word_counts)

def get_valid_date():
    while True:
        date_input = input("日付を 'YYYY-MM-DD' 形式で入力してください: ")
        try:
            # 日付形式をチェック
            date = datetime.strptime(date_input, "%Y-%m-%d").date()
            return date_input  # 入力が正しければ返す
        except ValueError:
            print("日付の形式が正しくありません。もう一度お試しください。")

if __name__ == "__main__":
    target_date = get_valid_date()  # 日付の入力を待機
    process_speeches(target_date)
