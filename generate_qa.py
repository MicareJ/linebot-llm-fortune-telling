# -*- coding: utf-8 -*-
import re
import json
import numpy as np
from sklearn.cluster import KMeans
from sentence_transformers import SentenceTransformer

def read_file(file_path):
    """讀取文本檔案"""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()
    except UnicodeDecodeError:
        # 如果UTF-8讀取失敗，嘗試使用Big5編碼
        with open(file_path, 'r', encoding='big5') as file:
            return file.read()
    except Exception as e:
        print(f"讀取檔案時發生錯誤: {e}")
        return ""

def segment_text(text):
    """將文本分割成有意義的片段"""
    # 先清理文本
    text = re.sub(r'\s+', ' ', text)  # 標準化空白
    text = re.sub(r'([。！？；])', r'\1\n', text)  # 在標點後添加換行
    
    # 分割成段落
    raw_segments = text.split('\n')
    
    # 清理和過濾片段
    segments = []
    for segment in raw_segments:
        segment = segment.strip()
        if len(segment) > 10:  # 只保留有足夠長度的片段
            segments.append(segment)
    
    return segments

def cluster_segments(segments, n_clusters=None):
    """使用句子嵌入和KMeans對片段進行聚類"""
    # 加載句子轉換模型
    model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
    
    # 獲取嵌入
    embeddings = model.encode(segments)
    
    # 如果沒有指定聚類數量，使用啟發式方法確定
    if n_clusters is None:
        n_clusters = min(len(segments) // 3, 10)  # 預設每3個片段一個聚類，最多10個聚類
        n_clusters = max(n_clusters, 2)  # 至少2個聚類
    
    # 進行KMeans聚類
    kmeans = KMeans(n_clusters=n_clusters, random_state=42)
    cluster_labels = kmeans.fit_predict(embeddings)
    
    # 根據聚類標籤組織片段
    clusters = {}
    for i, label in enumerate(cluster_labels):
        if label not in clusters:
            clusters[label] = []
        clusters[label].append(segments[i])
    
    return clusters

def analyze_cluster_content(cluster):
    """分析聚類內容以確定主題和關鍵詞"""
    # 合併聚類中的所有文本
    combined_text = " ".join(cluster)
    
    # 定義主題關鍵詞
    topics = {
        "五格計算": ["五格", "天格", "地格", "人格", "外格", "總格", "筆劃"],
        "八字命理": ["八字", "天干", "地支", "命盤", "生辰"],
        "五行關係": ["五行", "金木水火土", "相生", "相克"],
        "姓名學": ["姓名", "取名", "改名"],
        "命運分析": ["命運", "運勢", "吉凶", "預測"]
    }
    
    # 計算每個主題的相關性得分
    scores = {}
    for topic, keywords in topics.items():
        score = sum(combined_text.count(kw) for kw in keywords)
        scores[topic] = score
    
    # 獲取得分最高的主題
    if any(scores.values()):
        main_topic = max(scores.items(), key=lambda x: x[1])[0]
    else:
        main_topic = "一般命理學概念"
    
    # 分析是否包含計算方法或定義
    has_method = any(term in combined_text for term in ["計算", "方法", "步驟", "如何"])
    has_definition = any(term in combined_text for term in ["是", "指", "定義", "概念"])
    
    # 返回分析結果
    return {
        "topic": main_topic,
        "is_method": has_method,
        "is_definition": has_definition
    }

def generate_question_for_cluster(cluster):
    """為聚類生成適當的問題"""
    # 分析聚類內容
    analysis = analyze_cluster_content(cluster)
    
    # 為不同類型的內容準備問題模板
    templates = {
        "五格計算": {
            True: [  # 方法類問題
                "如何計算五格？五格計算的方法是什麼？",
                "五格的計算步驟是什麼？各格如何計算？"
            ],
            False: [  # 概念類問題
                "什麼是五格計算？五格包含哪些內容？",
                "五格計算的意義是什麼？對運勢有什麼影響？"
            ]
        },
        "八字命理": {
            True: [
                "如何排八字命盤？八字計算方法是什麼？",
                "八字分析的步驟是什麼？如何解讀八字？"
            ],
            False: [
                "什麼是八字命理？八字包含哪些元素？",
                "八字命理的基本原理是什麼？有什麼意義？"
            ]
        },
        "五行關係": {
            True: [
                "五行相生相克的原理是什麼？如何應用？",
                "如何分析五行的平衡？不同五行組合代表什麼？"
            ],
            False: [
                "什麼是五行？五行之間有什麼關係？",
                "五行（金木水火土）的特性是什麼？如何影響命運？"
            ]
        },
        "姓名學": {
            True: [
                "如何根據姓名學選擇好名字？取名有什麼技巧？",
                "姓名分析的方法是什麼？如何評估名字的吉凶？"
            ],
            False: [
                "姓名學的基本理論是什麼？姓名如何影響命運？",
                "什麼是姓名學？姓名與個人命運有什麼關聯？"
            ]
        },
        "命運分析": {
            True: [
                "如何進行命理分析？需要考慮哪些因素？",
                "命運預測的方法有哪些？準確性如何？"
            ],
            False: [
                "命理學的基本概念是什麼？如何理解命運？",
                "命理分析能告訴我們什麼？有什麼意義？"
            ]
        }
    }
    
    # 選擇合適的問題模板
    topic = analysis["topic"]
    is_method = analysis["is_method"]
    
    # 如果找不到特定主題的模板，使用通用模板
    if topic not in templates:
        if is_method:
            return "這個命理學方法是如何運作的？有什麼應用？"
        else:
            return "這個命理學概念是什麼？有什麼意義？"
    
    # 從模板中隨機選擇一個問題
    import random
    return random.choice(templates[topic][is_method])

def create_qa_pairs_from_clusters(clusters):
    """從聚類創建問答對"""
    qa_pairs = []
    
    for cluster_id, segments in clusters.items():
        # 跳過太小的聚類
        if len(segments) < 2:
            continue
        
        # 生成問題
        question = generate_question_for_cluster(segments)
        
        # 將聚類內容格式化為答案
        answer = "\n\n".join(segments)
        
        # 創建問答對
        qa_pairs.append({
            "input": question,
            "output": answer
        })
    
    return qa_pairs

def main(input_file="data.txt", output_file="qa_pairs.json"):
    """主函數"""
    # 讀取文件
    text = read_file(input_file)
    if not text:
        print("無法讀取檔案或檔案為空")
        return
    
    # 分割文本
    segments = segment_text(text)
    print(f"從文本中提取出{len(segments)}個片段")
    
    # 如果片段太少，不進行聚類
    if len(segments) < 5:
        print("文本片段數量太少，無法進行有效聚類")
        return
    
    # 聚類分析
    clusters = cluster_segments(segments)
    print(f"將片段分成{len(clusters)}個聚類")
    
    # 創建問答對
    qa_pairs = create_qa_pairs_from_clusters(clusters)
    print(f"生成了{len(qa_pairs)}個問答對")
    
    # 保存為JSON檔案
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(qa_pairs, f, ensure_ascii=False, indent=2)
    
    print(f"已將問答對保存至{output_file}")
    
    # 顯示部分問答對作為預覽
    preview_count = min(3, len(qa_pairs))
    print(f"\n預覽前{preview_count}個問答對:")
    for i in range(preview_count):
        print(f"\n問題 {i+1}: {qa_pairs[i]['input']}")
        print(f"答案 {i+1} (前100字): {qa_pairs[i]['output'][:100]}...")

if __name__ == "__main__":
    main()