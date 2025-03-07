import requests
from bs4 import BeautifulSoup
import re
import os
import datetime
from urllib.parse import urljoin

class WebScraper:
    def __init__(self, url, remove_patterns=None, download_images=False, image_folder="images", output_dir="scraped_data", max_depth=3):
        self.url = url
        self.visited_urls = set()
        self.remove_patterns = remove_patterns if remove_patterns else []
        self.download_images = download_images
        self.image_folder = image_folder
        self.output_dir = output_dir  # 設定輸出資料夾
        self.max_depth = max_depth  # 限制最大爬取深度
        
        # 確保輸出資料夾存在
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_file = os.path.join(self.output_dir, f"scraped_text_{timestamp}.txt")  # 生成新的檔案名稱
        self.scraped_data = {}
        
        # 需要剔除的關鍵字（雜訊）
        self.noise_keywords = [
            "首頁", "會員登入", "選購商品", "服務條款", "隱私權政策", "連絡我們", "立即前往", "發佈時間", "閱讀更多", "返回列表", "最新消息" , 
            "Copyright 2011", "版權所有", "劍靈命理網", "本網站內容僅作為參考之用", "相關玄學命理分析無法證實其真實性與準確性", "本網站會員公開張貼或私下傳送的任何資料", "均由提供者自負責任", "其立場與本網站無關", "本網站不保証其合法性", "正確性", "完整性或品質",
            "閱讀文章 - 劍靈命理網",  "註冊" 
        ]

    def _fetch_page(self, url):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
        }
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                return BeautifulSoup(response.text, 'html.parser')
            print(f"Failed to retrieve page: {url}, Status Code: {response.status_code}")
        except requests.exceptions.ConnectionError:
            print(f"Skipping inaccessible URL (DNS issue): {url}")
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}")
        return None

    def extract_text(self, soup):
        if not soup:
            return ""
        
        for script in soup(["script", "style"]):
            script.decompose()
        
        text = soup.get_text(separator=' ')
        text = re.sub(r'\s+', ' ', text).strip()
        
        # 移除特殊字元、亂碼，但保留所有標點符號
        text = re.sub(r'[^\x00-\x7F\u4e00-\u9fff.,!?;:()\"\'…，。、；：？！「」『』《》—【】]+', ' ', text)  # 保留標點符號
        
        # 過濾掉包含噪音關鍵字的內容
        for keyword in self.noise_keywords:
            text = re.sub(rf'\b{keyword}\b', '', text)
        
        for pattern in self.remove_patterns:
            text = re.sub(pattern, '', text)
        
        return text.strip()
    
    def extract_links(self, soup, base_url):
        if not soup:
            return []
        
        links = set()
        for a_tag in soup.find_all('a', href=True):
            links.add(urljoin(base_url, a_tag['href']))
        
        return links
    
    def scrape(self, url, depth=0):
        if url in self.visited_urls:
            print(f"Already visited: {url}")
            return

        if depth >= self.max_depth:
            print(f"Max depth reached: {url}")
            return  # 達到最大深度，停止爬取

        if any(url.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".mp4", ".avi", ".mov"]):
            print(f"Skipping non-HTML file: {url}")
            return

        print(f"Scraping: {url} (Depth: {depth})")
        self.visited_urls.add(url)
        soup = self._fetch_page(url)
        if not soup:
            return
        
        text = self.extract_text(soup)
        links = self.extract_links(soup, url)

        print(f"Extracted {len(text)} characters from {url}")
        print(f"Found {len(links)} links")

        self.scraped_data[url] = {"text": text, "links": list(links)}

        with open(self.output_file, "a", encoding="utf-8") as f:
            f.write(f"Scraped URL: {url}\n")
            f.write("Extracted Text:\n")
            f.write(text + "\n\n")
        
        for link in links:
            self.scrape(link, depth + 1)  # 讓下一層的深度增加

    def get_scraped_data(self):
        return self.scraped_data

if __name__ == "__main__":
    url = input("Enter the URL to scrape: ")
    remove_patterns = [r'\(?\d{3}\) \d{3}-\d{4}', r'\d{3}-\d{3}-\d{4}']  # Example patterns for phone numbers
    scraper = WebScraper(url, remove_patterns, download_images=True, output_dir="scraped_data", max_depth=3)
    scraper.scrape(url)
    print(f"Scraping complete. Extracted text saved to {scraper.output_file}")