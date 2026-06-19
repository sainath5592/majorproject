from flask import Flask, render_template, request, url_for
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from transformers import pipeline
from langdetect import detect
from googletrans import Translator
from PIL import Image
import time
import os
import pyttsx3
import requests

app = Flask(__name__)
analyzer = SentimentIntensityAnalyzer()
translator = Translator()

# IMAGE CLASSIFIER
image_classifier = pipeline("image-classification")

os.makedirs("static/audio", exist_ok=True)
os.makedirs("static/uploads", exist_ok=True)

# ---------------- TEXT TO SPEECH ----------------
tts_texts = {
    "positive": "This is a positive review. You can buy this product.",
    "neutral": "This review is neutral. Check more details before deciding.",
    "negative": "This is a negative review. Better to avoid this product."
}

for label, text in tts_texts.items():
    path = f"static/audio/{label}.wav"
    if not os.path.exists(path):
        engine = pyttsx3.init()
        engine.save_to_file(text, path)
        engine.runAndWait()
        engine.stop()

# ---------------- DRIVER (FIXED) ----------------
def get_driver():
    options = Options()

    # ❌ DO NOT USE HEADLESS (Flipkart blocks it)
    # options.add_argument("--headless=new")

    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("start-maximized")
    options.add_argument("disable-infobars")
    options.add_argument("--disable-extensions")

    # ✅ IMPORTANT USER-AGENT
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

# =====================================================
# ✅ SECTION 2 FINAL FIX
# =====================================================

def clean_flipkart_url(url):
    if "?" in url:
        url = url.split("?")[0]
    return url.replace("/p/", "/product-reviews/")

def scrape_flipkart_reviews(url):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    product = {"title": None, "reviews": [], "images": [], "rating": None}

    url = clean_flipkart_url(url)

    driver = get_driver()
    driver.get(url)

    wait = WebDriverWait(driver, 15)

    # Title
    try:
        title = wait.until(EC.presence_of_element_located((By.TAG_NAME, "h1")))
        product["title"] = title.text
    except:
        product["title"] = "Unknown Product"

    # Scroll to load reviews
    for _ in range(5):
        driver.execute_script("window.scrollBy(0, 2000);")
        time.sleep(2)

    # Wait for reviews
    try:
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "ZmyHeo")))
    except:
        time.sleep(5)

    soup = BeautifulSoup(driver.page_source, "html.parser")

    # Reviews (fallbacks)
    reviews = soup.find_all("div", {"class": "ZmyHeo"})
    if not reviews:
        reviews = soup.find_all("div", {"class": "t-ZTKy"})
    if not reviews:
        reviews = soup.find_all("div", {"class": "_6K-7Co"})

    product["reviews"] = [r.get_text(strip=True) for r in reviews[:15]]

    # Images
    imgs = soup.find_all("img")
    product["images"] = [img.get("src") for img in imgs if img.get("src")][:5]

    driver.quit()
    return product

# ---------------- AMAZON (UNCHANGED) ----------------
def scrape_amazon_reviews(url):
    product = {"title": None, "reviews": [], "images": [], "rating": None}

    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.content, "html.parser")

    title = soup.find("span", {"id": "productTitle"})
    product["title"] = title.get_text(strip=True) if title else "Unknown Product"

    rating = soup.find("span", {"class": "a-icon-alt"})
    if rating:
        try:
            product["rating"] = float(rating.text.split()[0])
        except:
            pass

    reviews = soup.find_all("span", {"data-hook": "review-body"})
    product["reviews"] = [r.get_text(strip=True) for r in reviews[:15]]

    img = soup.find("img", {"id": "landingImage"})
    if img:
        product["images"].append(img.get("src"))

    return product

# ---------------- SENTIMENT ----------------
def analyze_text(text):
    scores = analyzer.polarity_scores(text)
    c = scores["compound"]

    if c > 0.2:
        label = "Positive"
    elif c < -0.2:
        label = "Negative"
    else:
        label = "Neutral"

    return {
        "text": text,
        "scores": scores,
        "label": label,
        "image": f"images/{label.lower()}.png",
        "audio": f"audio/{label.lower()}.wav",
    }

def get_overall_sentiment(analyzed_reviews):
    pos = sum(1 for r in analyzed_reviews if r["label"] == "Positive")
    neg = sum(1 for r in analyzed_reviews if r["label"] == "Negative")
    total = len(analyzed_reviews)

    if total == 0:
        return {"label": "No Data", "decision": "No Reviews"}

    if pos / total > 0.6:
        return {"label": "Positive", "decision": "✅ Recommended (Buy)"}
    elif neg / total > 0.4:
        return {"label": "Negative", "decision": "❌ Not Recommended"}
    else:
        return {"label": "Neutral", "decision": "⚖️ Neutral (Check More)"}

# ---------------- SECTION 1 & 3 (UNCHANGED) ----------------

def analyze_multilingual(text):
    try:
        lang = detect(text)
    except:
        lang = "en"

    translated = translator.translate(text, dest="en").text
    scores = analyzer.polarity_scores(translated)

    if scores["compound"] > 0.2:
        label = "Positive"
    elif scores["compound"] < -0.2:
        label = "Negative"
    else:
        label = "Neutral"

    return {
        "original": text,
        "translated": translated,
        "label": label,
        "confidence": abs(scores["compound"]),
        "image": f"images/{label.lower()}.png",
        "audio": f"audio/{label.lower()}.wav",
    }

def classify_image(file_path):
    img = Image.open(file_path)
    res = image_classifier(img)[0]
    return {"label": res["label"], "confidence": res["score"]}

def get_product_links(query):
    return [
        {"title": f"Search {query} on Amazon", "link": f"https://www.amazon.in/s?k={query.replace(' ', '+')}"},
        {"title": f"Search {query} on Flipkart", "link": f"https://www.flipkart.com/search?q={query.replace(' ', '+')}"},
        {"title": f"Search {query} on Myntra", "link": f"https://www.myntra.com/{query.replace(' ', '-')}"},
        {"title": f"Search {query} on Google Shopping", "link": f"https://www.google.com/search?tbm=shop&q={query.replace(' ', '+')}"}
    ]

# ---------------- ROUTE ----------------

@app.route("/", methods=["GET", "POST"])
def index():
    text_result = None
    multi_result = None
    chart_data = None
    image_result = None
    product_links = []
    product = None
    analyzed_reviews = []
    overall_result = None

    if request.method == "POST":
        text_input = request.form.get("text")
        language = request.form.get("language")
        url_input = request.form.get("url")

        # SECTION 1
        if text_input:
            if language == "en":
                text_result = analyze_text(text_input)
            else:
                multi_result = analyze_multilingual(text_input)

        # ✅ SECTION 2 FIXED
        if url_input:
            if "flipkart" in url_input:
                product = scrape_flipkart_reviews(url_input)
            elif "amazon" in url_input:
                product = scrape_amazon_reviews(url_input)

            if product and product["reviews"]:
                analyzed_reviews = [analyze_text(r) for r in product["reviews"]]
                overall_result = get_overall_sentiment(analyzed_reviews)
            else:
                overall_result = {"label": "No Data", "decision": "No Reviews Found"}

        # SECTION 3
        if "product_image" in request.files:
            file = request.files["product_image"]

            if file and file.filename:
                filepath = os.path.join("static/uploads", file.filename)
                file.save(filepath)

                image_result = classify_image(filepath)
                query = image_result["label"]
                product_links = get_product_links(query)

    return render_template(
        "index.html",
        text_result=text_result,
        multi_result=multi_result,
        chart_data=chart_data,
        image_result=image_result,
        product_links=product_links,
        product=product,
        analyzed_reviews=analyzed_reviews,
        overall_result=overall_result
    )

if __name__ == "__main__":
    app.run(debug=True)