import requests
from bs4 import BeautifulSoup
import time
import os
import re
from urllib.parse import urljoin, quote, unquote

class NameFateScraper:
    def __init__(self, base_url, output_dir="scraped_data"):
        self.base_url = base_url
        self.output_dir = output_dir
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        })
        
        # 确保输出目录存在
        os.makedirs(output_dir, exist_ok=True)
            
        # 存储已爬取的文章URL
        self.crawled_articles = set()
        
        # 所有文章内容将直接合并在这个字符串中
        self.all_content = ""
        self.article_count = 0
    
    def get_page(self, url):
        """获取页面内容"""
        try:
            print(f"Fetching: {url}")
            response = self.session.get(url)
            response.raise_for_status()
            response.encoding = 'utf-8'
            return response.text
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            return None
    
    def extract_article_links_from_page(self, category_url, page_number=1):
        """专门查找class='ct-media-container boundless-image'的链接元素"""
        # 构建分页URL
        if page_number > 1:
            page_url = f"{category_url}page/{page_number}/"
        else:
            page_url = category_url
            
        print(f"Extracting articles from page URL: {page_url}")
        html = self.get_page(page_url)
        if not html:
            return []
        
        soup = BeautifulSoup(html, 'html.parser')
        article_links = []
        
        # 直接查找所有具有特定类名的链接元素
        # 使用精确的类名组合查询
        media_links = soup.select('a.ct-media-container.boundless-image')
        print(f"Found {len(media_links)} media container links on page")
        
        for link in media_links:
            if link.has_attr('href'):
                href = link.get('href')
                # 提取链接和标题
                title = link.get('aria-label', '')
                # 添加到结果列表
                article_links.append(href)
                print(f"Found article: '{title}' at {href}")
        
        # 如果没有找到链接，尝试分别查找每个类
        if not article_links:
            print("No exact class match found. Trying individual classes...")
            individual_links = soup.select('a.ct-media-container, a.boundless-image')
            
            for link in individual_links:
                if link.has_attr('href'):
                    href = link.get('href')
                    title = link.get('aria-label', '')
                    if '/category/' in href and not href.endswith('/category/') and not '/page/' in href:
                        article_links.append(href)
                        print(f"Found article with individual class: '{title}' at {href}")
        
        # 如果仍然找不到链接，尝试查找包含图片的链接
        if not article_links:
            print("Still no links found. Trying image-containing links...")
            # 查找所有包含wp-post-image类的图片的父链接
            img_elements = soup.select('img.wp-post-image')
            
            for img in img_elements:
                # 查找父元素是否为链接
                parent = img.parent
                if parent.name == 'a' and parent.has_attr('href'):
                    href = parent.get('href')
                    title = parent.get('aria-label', '')
                    if '/category/' in href and not href.endswith('/category/') and not '/page/' in href:
                        article_links.append(href)
                        print(f"Found article with image: '{title}' at {href}")
        
        # 去重
        unique_links = list(set(article_links))
        print(f"Total unique article links found: {len(unique_links)}")
        return unique_links
    
    def extract_article_content(self, url):
        """提取文章内容，移除目录和相关链接后的内容"""
        html = self.get_page(url)
        if not html:
            return None
        
        # 记录原始URL以便调试
        print(f"Extracting content from: {url}")
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # 先移除Table of Contents
        toc_container = soup.select_one('#ez-toc-container')
        if toc_container:
            print("Removing Table of Contents")
            toc_container.decompose()
        
        # 提取文章标题
        title_element = soup.select_one('h1.entry-title, .article-title, .post-title, .entry-header h1')
        has_title = title_element is not None
        title = title_element.text.strip() if has_title else ""
        if has_title:
            print(f"Found article title: {title}")
        
        # 提取文章内容 - 使用更广泛的选择器以确保捕获所有内容
        content_element = soup.select_one('.entry-content, .post-content, .article-content, .content, .single-content, #primary')
        
        cleaned_content = ""
        
        if content_element:
            # 移除不需要的元素
            for element in content_element.select('script, style, .advertisement, .ads, .related-posts, .share-buttons, .comments, .ez-toc-container, .ez-toc, #ez-toc-container, .wp-block-code'):
                element.decompose()
            
            # 只有在有标题的情况下才添加标题
            if has_title:
                cleaned_content = title + "\n\n"
            
            # 获取所有HTML内容
            html_content = str(content_element)
            
            # 检查是否包含相关链接标记，并截取之前的内容
            contains_related_links = False
            truncated_html = html_content
            marker = ""
            
            # 检查各种可能的相关链接标记 (扩展多种可能的变体)
            related_markers = [
                "相关链接", "相關連結", "相關鏈接", "相關文章", "相關資料", "相關推薦", 
                "延伸閱讀", "延伸阅读", "推薦閱讀", "推荐阅读", "其他文章", "更多文章",
                "参考链接", "參考連結"
            ]
            
            for marker_text in related_markers:
                if marker_text in html_content:
                    contains_related_links = True
                    marker = marker_text
                    index = html_content.find(marker_text)
                    
                    # 找到包含标记的段落或div的开始位置
                    for i in range(index, 0, -1):
                        if html_content[i:i+4] == "<div" or html_content[i:i+2] == "<p" or html_content[i:i+3] == "<h2" or html_content[i:i+3] == "<h3" or html_content[i:i+3] == "<ul" or html_content[i:i+4] == "<nav":
                            truncated_html = html_content[:i]
                            print(f"Found marker '{marker_text}' - truncating content at position {i}")
                            break
                    else:
                        # 如果找不到开始标签，就直接在标记处截断
                        truncated_html = html_content[:index]
                        print(f"Found marker '{marker_text}' - truncating directly at position {index}")
                    break
            
            if contains_related_links:
                # 解析截断后的HTML
                truncated_soup = BeautifulSoup(truncated_html, 'html.parser')
                
                # 提取文本 - 获取所有文本节点，确保完整性
                paragraphs = truncated_soup.find_all(['p', 'h2', 'h3', 'h4', 'li', 'blockquote', 'div.paragraph', 'div.text', 'span.text', 'div.content'])
                if paragraphs:
                    content_pieces = []
                    for p in paragraphs:
                        text = p.text.strip()
                        if text:  # 只添加非空内容
                            content_pieces.append(text)
                    cleaned_content += "\n\n".join(content_pieces)
                else:
                    # 如果找不到段落标签，直接获取文本
                    cleaned_content += truncated_soup.get_text(separator="\n\n", strip=True)
                
                print(f"Extracted content until '{marker}', length: {len(cleaned_content)} chars")
            else:
                # 如果找不到"相关链接"，使用完整内容
                # 使用更全面的内容提取方法
                paragraphs = content_element.find_all(['p', 'h2', 'h3', 'h4', 'li', 'blockquote', 'div.paragraph', 'div.text', 'span.text', 'div.content'])
                if paragraphs:
                    content_pieces = []
                    for p in paragraphs:
                        text = p.text.strip()
                        if text:  # 只添加非空内容
                            content_pieces.append(text)
                    cleaned_content += "\n\n".join(content_pieces)
                else:
                    # 如果仍然找不到内容，使用通用方法
                    cleaned_content += content_element.get_text(separator="\n\n", strip=True)
                print("No related links markers found, using full content")
            
        else:
            # 如果找不到内容元素，尝试查找主要内容区域，采用更广泛的选择器
            print("No standard content element found, trying to find main content area")
            main_content = soup.select_one('main, #content, article, .site-main, .site-content, .main-content, #main-content')
            if main_content:
                # 移除不需要的元素，包括TOC
                for element in main_content.select('script, style, .advertisement, .comments, .sidebar, nav, footer, #ez-toc-container, .ez-toc-container, .ez-toc'):
                    element.decompose()
                
                # 只有在有标题的情况下才添加标题
                if has_title:
                    cleaned_content = title + "\n\n"
                
                # 检查"相关链接"并截断 - 类似上面的处理方式
                html_content = str(main_content)
                contains_related_links = False
                truncated_html = html_content
                marker = ""
                
                for marker_text in related_markers:
                    if marker_text in html_content:
                        contains_related_links = True
                        marker = marker_text
                        index = html_content.find(marker_text)
                        for i in range(index, 0, -1):
                            if html_content[i:i+4] == "<div" or html_content[i:i+2] == "<p" or html_content[i:i+3] == "<h2" or html_content[i:i+3] == "<h3" or html_content[i:i+3] == "<ul" or html_content[i:i+4] == "<nav":
                                truncated_html = html_content[:i]
                                print(f"Found marker '{marker_text}' in main content - truncating at position {i}")
                                break
                        else:
                            truncated_html = html_content[:index]
                            print(f"Found marker '{marker_text}' in main content - truncating directly at position {index}")
                        break
                
                if contains_related_links:
                    truncated_soup = BeautifulSoup(truncated_html, 'html.parser')
                    paragraphs = truncated_soup.find_all(['p', 'h2', 'h3', 'h4', 'li', 'blockquote', 'div.paragraph', 'div.text', 'span.text', 'div.content'])
                    if paragraphs:
                        content_pieces = []
                        for p in paragraphs:
                            text = p.text.strip()
                            if text:
                                content_pieces.append(text)
                        cleaned_content += "\n\n".join(content_pieces)
                    else:
                        cleaned_content += truncated_soup.get_text(separator="\n\n", strip=True)
                else:
                    paragraphs = main_content.find_all(['p', 'h2', 'h3', 'h4', 'li', 'blockquote', 'div.paragraph', 'div.text', 'span.text', 'div.content'])
                    if paragraphs:
                        content_pieces = []
                        for p in paragraphs:
                            text = p.text.strip()
                            if text:
                                content_pieces.append(text)
                        cleaned_content += "\n\n".join(content_pieces)
                    else:
                        cleaned_content += main_content.get_text(separator="\n\n", strip=True)
        
        # 最终清理
        # 删除多余的空白行
        cleaned_content = re.sub(r'\n{3,}', '\n\n', cleaned_content)
        # 删除连续的空格
        cleaned_content = re.sub(r' {2,}', ' ', cleaned_content)
        
        # 返回清理后的内容
        if cleaned_content.strip():
            print(f"Successfully extracted content, length: {len(cleaned_content.strip())} chars")
            return cleaned_content.strip()
        else:
            print("Failed to extract any content")
            return None
    
    def append_article(self, content):
        """将文章内容添加到总内容字符串中"""
        if not content:
            return False
        
        self.article_count += 1
        self.all_content += f"\n\n--- 文章 {self.article_count} ---\n\n"
        self.all_content += content
        self.all_content += "\n\n"
        
        # 每爬取10篇文章，保存一次进度
        if self.article_count % 10 == 0:
            self.save_content()
            print(f"Progress saved: {self.article_count} articles so far")
        
        return True
    
    def save_content(self):
        """保存所有内容到一个文件"""
        # 确保输出目录存在
        os.makedirs(self.output_dir, exist_ok=True)
        
        file_path = os.path.join(self.output_dir, "data.txt")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(self.all_content)
    
    def crawl_category(self, category, max_pages=None, delay=2):
        """爬取特定分类的所有页面和文章"""
        category_url = f"{self.base_url}/category/{category}/"
        print(f"Crawling category: {category_url}")
        
        page_number = 1
        total_articles = 0
        consecutive_empty_pages = 0
        
        while max_pages is None or page_number <= max_pages:
            # 获取当前页面的所有文章链接
            article_links = self.extract_article_links_from_page(category_url, page_number)
            
            # 如果没有找到文章链接，尝试再次获取（有时是临时错误）
            if not article_links and page_number == 1:
                print("First page returned no articles. Retrying...")
                time.sleep(delay * 2)
                article_links = self.extract_article_links_from_page(category_url, page_number)
            
            # 如果仍然没有文章，记录连续空页面
            if not article_links:
                consecutive_empty_pages += 1
                print(f"No articles found on page {page_number}. Empty pages count: {consecutive_empty_pages}")
                
                # 如果连续3个页面都没有文章，可能已到达最后页
                if consecutive_empty_pages >= 3:
                    print(f"Reached 3 consecutive empty pages, ending pagination.")
                    break
                    
                # 继续尝试下一页
                page_number += 1
                time.sleep(delay)
                continue
            
            # 找到文章，重置空页面计数
            consecutive_empty_pages = 0
            
            print(f"Found {len(article_links)} articles on page {page_number}")
            
            # 爬取每篇文章
            for article_url in article_links:
                if article_url in self.crawled_articles:
                    print(f"Skipping already crawled article: {article_url}")
                    continue
                
                article_content = self.extract_article_content(article_url)
                if article_content:
                    self.append_article(article_content)
                    total_articles += 1
                    print(f"Added article {self.article_count} from {article_url}")
                
                self.crawled_articles.add(article_url)
                time.sleep(delay)  # 延迟，避免请求过于频繁
            
            # 移动到下一页
            page_number += 1
            
            # 页面间延迟
            time.sleep(delay)
        
        print(f"Finished crawling category {category}, found {total_articles} articles")
        return total_articles
    
    def crawl_categories(self, categories, max_pages_per_category=None, delay=2):
        """爬取多个分类的所有文章"""
        total_articles = 0
        
        for category in categories:
            articles = self.crawl_category(category, max_pages_per_category, delay)
            total_articles += articles
        
        # 最终保存内容
        self.save_content()
        
        print(f"Crawling completed. Total articles across all categories: {total_articles}")
        return os.path.join(self.output_dir, "data.txt")

# 使用示例
if __name__ == "__main__":
    # 初始化爬虫
    scraper = NameFateScraper("https://namefate.erigance.com.tw")
    
    # 爬取多个分类
    categories = ["name-basics", "name-fortune"]
    output_file = scraper.crawl_categories(categories, max_pages_per_category=None, delay=2)
    
    print(f"All articles have been saved to: {output_file}")

