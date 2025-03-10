from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
import random
import json
import time

# 讀取中文姓名JSON文件
def get_random_name():
    with open('chinese_name.json', 'r', encoding='utf-8') as file:
        names_data = json.load(file)
        
        # 根據JSON文件結構調整以下代碼
        # 假設JSON格式為簡單的姓名列表 ["王小明", "李小華", ...]
        if isinstance(names_data, list):
            random_name = random.choice(names_data)
        # 假設JSON格式為 {"names": ["王小明", "李小華", ...]}
        elif isinstance(names_data, dict) and "names" in names_data:
            random_name = random.choice(names_data["names"])
        # 其他可能的格式，請根據實際情況調整
        else:
            # 遍歷尋找可能包含姓名的列表
            for key, value in names_data.items():
                if isinstance(value, list) and len(value) > 0:
                    random_name = random.choice(value)
                    break
            else:
                raise ValueError("無法從JSON文件中找到有效的姓名列表")
    
    # 分離姓氏和名字
    surname = random_name[0]  # 第一個字為姓氏
    given_name = random_name[1:]  # 剩餘部分為名字
    
    return surname, given_name

# 設定瀏覽器驅動
driver = webdriver.Chrome()  # 您也可以使用Firefox、Edge等

try:
    # 前往目標網頁
    driver.get("https://www.sheup.org/rizhu_lunming.php")  # 替換成實際的URL
    
    # 等待頁面加載
    wait = WebDriverWait(driver, 2)
    
    # 隨機選擇姓名
    surname, given_name = get_random_name()
    print(f"隨機選擇的姓名: {surname}{given_name}")
    
    # 定位並填寫姓氏欄位
    surname_field = wait.until(EC.presence_of_element_located((By.NAME, "xing")))
    surname_field.send_keys(surname)
    
    # 定位並填寫名字欄位
    name_field = driver.find_element(By.NAME, "ming")
    name_field.send_keys(given_name)
    
    # 隨機選擇性別
    gender_options = ["男", "女"] 
    random_gender = random.choice(gender_options)
    gender_dropdown = Select(driver.find_element(By.NAME, "sex"))
    
    # 嘗試使用多種可能的方式選擇性別
    try:
        gender_dropdown.select_by_visible_text(random_gender)
    except:
        try:
            gender_dropdown.select_by_value(random_gender)
        except:
            # 如果以上方法失敗，選擇索引
            gender_dropdown.select_by_index(0 if random_gender == "男" else 1)
    
    print(f"選擇的性別: {random_gender}")
    
    # 隨機選擇年份 (1949-2024)
    random_year = str(random.randint(1949, 2024))
    year_dropdown = Select(driver.find_element(By.NAME, "nian"))
    
    # 嘗試選擇年份
    try:
        year_dropdown.select_by_value(random_year)
    except:
        try:
            year_dropdown.select_by_visible_text(random_year)
        except:
            # 找到所有年份選項
            options = year_dropdown.options
            selected_index = random.randint(0, len(options)-1)
            year_dropdown.select_by_index(selected_index)
            random_year = options[selected_index].text
    
    print(f"選擇的年份: {random_year}")
    
    # 隨機選擇月份 (1-12)
    random_month = str(random.randint(1, 12))
    month_dropdown = Select(driver.find_element(By.NAME, "yue"))
    
    try:
        month_dropdown.select_by_value(random_month)
    except:
        try:
            month_dropdown.select_by_visible_text(random_month)
        except:
            # 選擇隨機索引
            options = month_dropdown.options
            selected_index = random.randint(0, len(options)-1)
            month_dropdown.select_by_index(selected_index)
            random_month = options[selected_index].text
    
    print(f"選擇的月份: {random_month}")
    
    # 根據月份決定日期範圍
    month_num = int(random_month) if random_month.isdigit() else random.randint(1, 12)
    
    days_in_month = {
        1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30,
        7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31
    }
    
    # 處理閏年二月
    year_num = int(random_year) if random_year.isdigit() else 2000
    if month_num == 2 and (year_num % 4 == 0 and year_num % 100 != 0 or year_num % 400 == 0):
        max_day = 29
    else:
        max_day = days_in_month[month_num]
    
    # 隨機選擇日期
    random_day = str(random.randint(1, max_day))
    day_dropdown = Select(driver.find_element(By.NAME, "ri"))
    
    try:
        day_dropdown.select_by_value(random_day)
    except:
        try:
            day_dropdown.select_by_visible_text(random_day)
        except:
            options = day_dropdown.options
            selected_index = random.randint(0, len(options)-1)
            day_dropdown.select_by_index(selected_index)
            random_day = options[selected_index].text
    
    print(f"選擇的日期: {random_day}")
    
    # 點擊提交按鈕 (name="suanming")
    submit_button = driver.find_element(By.NAME, "suanming")
    submit_button.click()
    
    # 等待跳轉到新頁面完成
    wait.until(EC.url_changes(driver.current_url))
    print(f"已跳轉到新頁面: {driver.current_url}")
    
    # 這裡是抓取結果頁面數據的部分，稍後可根據需要修改
    # 示例: 抓取頁面標題
    print(f"新頁面標題: {driver.title}")
    
    # 示例: 抓取頁面上的所有文本
    page_text = driver.find_element(By.TAG_NAME, "body").text
    print("頁面文本摘要 (前200字):", page_text[:200])
    
    # 稍後可以根據需要添加更具體的數據抓取邏輯
    # 例如:
    # result_element = wait.until(EC.presence_of_element_located((By.ID, "specific-id")))
    # specific_data = result_element.text
    # print("抓取的特定數據:", specific_data)
    
except Exception as e:
    print(f"發生錯誤: {e}")
    import traceback
    traceback.print_exc()
    
finally:
    # 如果需要保留瀏覽器窗口查看結果，請註釋掉下面這行
    driver.quit()