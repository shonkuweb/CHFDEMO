import requests

# 1. Update the home trends description to remove the instruction
trends_payload = {
    "badge_label": "The Current Landscape",
    "title_line1": "Botanical",
    "title_highlight": "Trends",
    "title_connector": "for the",
    "title_line3": "Modern Collector",
    "description": "An editorial perspective on biophilic living - where curated planting and architectural design shape immersive contemporary spaces."
}

res1 = requests.post("http://localhost:8000/api/home-trends-section/save", json=trends_payload)
print("Trends save:", res1.json())

# 2. Fetch current site content to update card3
res2 = requests.get("http://localhost:8000/api/site-content?page=home")
site_content = res2.json()

# Make sure we have the structure
if "home/trends/card3/body" not in site_content:
    site_content["home/trends/card3/body"] = {"type": "longtext", "value": ""}

# Add the requested text
site_content["home/trends/card3/body"]["value"] = "Engineered green screens, floating green serenity, and vertical gardens that redefine internal boundaries."

res3 = requests.post("http://localhost:8000/api/site-content/save", json=site_content)
print("Site content save:", res3.json())

