import os
import re
import time
import shutil
import pathlib
import requests

from tqdm import tqdm
from playwright.sync_api import sync_playwright

# Manga directory from HOME
MANGA_DIR = "Manga/"
MANGA_URL = "" # Empty for user input

DECORATIVE_DELAY = 0.01
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

# Validate URL
if not mangaURL or not mangaURL.startswith(('http://', 'https://')):
    print("Error: Please provide a valid URL starting with http:// or https://")
    exit(1)

# Playwright setup
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    page.set_default_timeout(10000)

    # Navigate to the manga page
    page.goto(mangaURL)

    # Get basic information about the manga
    try:
        page.wait_for_selector('.UAname')
        mangaName = page.locator(".UAname").text_content()
        if not mangaName:
            print("Error: Could not extract manga name")
            exit(1)
        print(f"Name: {mangaName}")

        page.wait_for_selector('.circle-progress-text-max')
        mangaChapterCount = page.locator(".circle-progress-text-max").first.text_content()
        print("Chapter Count:", mangaChapterCount or "Unknown")

        page.wait_for_selector('.item__full-sidebar--description')
        mangaAge = page.locator(".item__full-sidebar--description").first.text_content()
        print("Age: ", mangaAge or "Unknown")
    except Exception as e:
        print(f"Error extracting manga information: {e}")
        exit(1)

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
        try:
            chapterName = pageChapters.locator(".ltcitems").nth(i).locator("a").last.text_content()
            chapterLink = pageChapters.locator(".ltcitems").nth(i).locator("a").last.get_attribute('href')
            if chapterLink:
                chapters.append(chapterLink)
                print(f"Chapter {i+1}: {chapterName or 'Unknown'}")
                print(f"    URL: {chapterLink}")
            else:
                print(f"Warning: Could not extract link for chapter {i+1}")
        except Exception as e:
            print(f"Warning: Error extracting chapter {i+1}: {e}")
        time.sleep(DECORATIVE_DELAY)

    # Get pictures links
    mangaDict = {}
    mangaDict['title'] = mangaName

    for i, chapter in enumerate(tqdm(chapters, desc="Getting pictures links")):
        if i < 10:
            chapterDictKey = f"00{i}"
        elif i < 100:
            chapterDictKey = f"0{i}"
        else:
            chapterDictKey = f"{i}"
        mangaDict[chapterDictKey] = {}

        chapterPage = context.new_page()
        try:
            chapterPage.goto(chapter)
            time.sleep(1)

            chapterPage.get_by_text("Читати розділ").click()
            chapterPage.wait_for_selector("#comics")

            chapterNameElement = chapterPage.locator(".fastcomicsnavigatontop").locator(".youreadnow").first.text_content()
            chapterName = chapterNameElement.replace(f"Ви читаєте: {mangaName} - ", "").strip() if chapterNameElement else f"Chapter {i+1}"
            mangaDict[chapterDictKey]["name"] = chapterName
            mangaDict[chapterDictKey]["url"] = chapter

            # Get images
            imageUrls = []
            imagesList = chapterPage.locator("#comics").locator(".xfieldimagegallery")
            count = imagesList.locator("li").count()
            for j in range(count):
                imageSrc = chapterPage.locator(f"#comicspage{j+1}").get_attribute("data-src")
                if imageSrc:
                    imageUrls.append(imageSrc)
            mangaDict[chapterDictKey]["images"] = imageUrls
        except Exception as e:
            print(f"Warning: Error processing chapter {i+1}: {e}")
            mangaDict[chapterDictKey]["images"] = []
        finally:
            # Close tab to save RAM
            chapterPage.close()

    # Close browser
    browser.close()

    # Download images
    # Filename example: "Okusama wa Shougakusei c003 (v01)"
    for chapterKey, chapterData in mangaDict.items():
        if chapterKey == "title":
            continue

        volumeMatch = re.search(r'tom-(\d+)', chapterData["url"], re.IGNORECASE)
        if volumeMatch:
            volumeNumber = int(volumeMatch.group(1))
            if volumeNumber < 10:
                volumeNumber = "0" + str(volumeNumber)
            else:
                volumeNumber = str(volumeNumber)
        else:
            # Default to 01 if volume number cannot be extracted
            volumeNumber = "01"

        fileName = f"{mangaName} c{chapterKey} (v{volumeNumber})"

        # Create temp dir for pictures before archive
        tempDir = os.path.join(mangaDirectory, "temp")
        if not os.path.exists(tempDir):
            os.makedirs(tempDir)

        # Download images
        imageUrls = chapterData["images"]
        for i, imageUrl in enumerate(tqdm(imageUrls, desc=f"Downloading chapter {chapterKey}")):
            try:
                # Get file extension from URL
                extension = imageUrl.split(".")[-1] if "." in imageUrl else "jpg"
                response = requests.get(imageUrl, timeout=30)
                response.raise_for_status()
                image = response.content

                if "404 Not Found" in str(image) or len(image) < 1000:  # Skip if likely error or too small
                    continue

                if i < 10:
                    filenum = f"0{i}"
                else:
                    filenum = str(i)
                
                with open(f"{tempDir}/{filenum}.{extension}", "wb") as f:
                    f.write(image)
            except Exception as e:
                print(f"Warning: Failed to download image {i+1}: {e}")
                continue
        
        # Create cbz archive
        try:
            if os.listdir(tempDir):  # Only create archive if temp dir has files
                shutil.make_archive(f"{mangaDirectory}/{fileName}", "zip", tempDir)
                os.rename(f"{mangaDirectory}/{fileName}.zip", f"{mangaDirectory}/{fileName}.cbz")
                print(f"Created: {fileName}.cbz")
            else:
                print(f"Warning: No images downloaded for chapter {chapterKey}")
        except Exception as e:
            print(f"Error creating archive for chapter {chapterKey}: {e}")
        finally:
            # Clean up temporary directory
            if os.path.exists(tempDir):
                shutil.rmtree(tempDir)      
