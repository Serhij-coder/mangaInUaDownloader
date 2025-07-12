import os
import re
import time
import json
import shutil
import pathlib
import requests

from tqdm import tqdm
from playwright.sync_api import sync_playwright

# Manga directory from HOME
MANGA_DIR = "Manga/"
MANGA_URL = "https://manga.in.ua/mangas/boyovik/105-tokiiskyi-gul.html" # Empty for user input

DECORATIVE_DELAY = 0.05
LOAD_DELAY = 0.3

# Control or create "Manga" folder
home = os.getenv('HOME')
mangaFolder = os.path.join(home, 'Manga')

if not os.path.exists(mangaFolder):
    print(f"The directory {mangaFolder} does not exist. Creating it...")
    os.makedirs(mangaFolder)
print(f"The directory {mangaFolder} exists.")

# Get manga page URL from user input
if not MANGA_URL:
    mangaURL = input("Enter the URL of the manga you want to download: ")
else:
    print("Using provided URL:", MANGA_URL)
    mangaURL = MANGA_URL

# Playwright setup
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    page.set_default_timeout(10000)

    # Navigate to the manga page
    page.goto(mangaURL)

    # Get basic information about the manga
    page.wait_for_selector('.UAname')
    mangaName = page.locator(".UAname").text_content()
    print(f"Name: {mangaName}")

    page.wait_for_selector('.circle-progress-text-max')
    mangaChapterCount  = page.locator(".circle-progress-text-max").first.text_content()
    print("Chapter Count:", mangaChapterCount)

    page.wait_for_selector('.item__full-sidebar--description')
    mangaAge = page.locator(".item__full-sidebar--description").first.text_content()
    print("Age: ", mangaAge)

    mangaNameLatin = mangaURL.split('/')[-1].replace('.html', '')
    mangaNameLatin = re.sub(r'^\d+-', '', mangaNameLatin)
    print("Manga Name Latin:", mangaNameLatin)

    # Create directory for the manga
    mangaDirectory = os.path.join(mangaFolder, mangaName)
    if not os.path.exists(mangaDirectory):
        os.makedirs(mangaDirectory)
    else:
        inp = input(f"Directory already exists: {mangaDirectory} want to overwrite? [Y/n] ").lower()
        if inp == 'y' or inp == '':
            shutil.rmtree(mangaDirectory)
            os.makedirs(mangaDirectory)
        else:
            exit(1)

    # Find all chapters and their URLs
    chapters = []
    page.wait_for_selector('#linkstocomics')
    pageChapters = page.locator('#linkstocomics')

    chaptersCount = pageChapters.locator(".ltcitems").count()
    for i in range(chaptersCount):
        chapterName = pageChapters.locator(".ltcitems").nth(i).locator("a").last.text_content()
        chapterLink = pageChapters.locator(".ltcitems").nth(i).locator("a").last.get_attribute('href')
        chapters.append(chapterLink)
        print(f"Chapter {i+1}: {chapterName}")
        print(f"    URL: {chapterLink}")
        time.sleep(DECORATIVE_DELAY)

    # Get pictures links
    mangaDict = {}
    mangaDict['title'] = mangaName

    for i, chapter in enumerate(tqdm(chapters, desc="Getting pictures links")):
        chapterDictKey = f'chapter{i}'
        mangaDict[chapterDictKey] = {}

        chapterPage = context.new_page()
        chapterPage.goto(chapter)
        time.sleep(1)

        chapterPage.get_by_text("Читати розділ").click()
        chapterPage.wait_for_selector("#comics")

        mangaDict[chapterDictKey]["name"] = chapterPage.locator(".fastcomicsnavigatontop").locator(".youreadnow").first.text_content().replace(f"Ви читаєте: {mangaName} - ", "").strip()
        mangaDict[chapterDictKey]["url"] = chapter

        # Отримати картинки
        imageUrls = []
        imagesList = chapterPage.locator("#comics").locator(".xfieldimagegallery")
        count = imagesList.locator("li").count()
        for j in range(count):
            imageUrls.append(chapterPage.locator(f"#comicspage{j+1}").get_attribute("data-src"))
        mangaDict[chapterDictKey]["images"] = imageUrls
        
        # Close tab to save RAM
        chapterPage.close()

    print(json.dumps(mangaDict, ensure_ascii=False, indent=4))

    inp = input("Want to save JSON file? [y/N]: ").lower()
    if inp == "y":
        with open(f"{mangaDirectory}/{mangaNameLatin}.json", "w") as json_file:
            json.dump(mangaDict, json_file, ensure_ascii=False, indent=4)
            print("JSON file saved successfully.")
    else:
        print("JSON file not saved.")

    # Close browser
    browser.close()

    # Download images
    for chapterKey, chapterData in tqdm(mangaDict.items(), desc="Downloading images"):
        if chapterKey == "title":
            continue

        chapterName = chapterData["name"]
        chapterPath = os.path.join(mangaDirectory, chapterName)

        os.makedirs(chapterPath, exist_ok=True)

        #<--Chat GPT-->
        for i, imageUrl in enumerate(chapterData["images"]):
            # Отримуємо розширення файлу
            ext = os.path.splitext(imageUrl)[1]
            image_path = os.path.join(chapterPath, f"{i:03d}{ext}")

            # Завантаження зображення
            try:
                response = requests.get(imageUrl)
                response.raise_for_status()

                with open(image_path, "wb") as f:
                    f.write(response.content)
            except Exception as e:
                ...
        #>--Chat GPT--<
