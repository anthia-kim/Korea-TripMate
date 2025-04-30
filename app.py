from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import requests
from config import SERVICE_KEY  # .env에서 API 키 불러오기

app = FastAPI()

# HTML 템플릿 폴더 설정
templates = Jinja2Templates(directory="templates")

# 카테고리에 맞는 한국관광공사 contentTypeId 매핑
CATEGORY_CODE_MAP = {
    "음식점": "39",    # 음식점
    "숙소": "32",      # 숙박
    "관광지": "12",    # 관광지
    "쇼핑": "38",      # 쇼핑
}

# ▶ 1. 카테고리 선택 페이지
@app.get("/", response_class=HTMLResponse)
async def select_category(request: Request):
    return templates.TemplateResponse("select_category.html", {"request": request})

# ▶ 2. 지역 선택 페이지 (시/도, 시군구)
@app.post("/select_region", response_class=HTMLResponse)
async def select_region(request: Request, category: str = Form(...)):
    return templates.TemplateResponse("select_region.html", {"request": request, "category": category})

# ▶ 3. 최종 추천 결과 페이지
@app.post("/show_recommendations", response_class=HTMLResponse)
async def show_recommendations(
    request: Request,
    category: str = Form(...),
    city: str = Form(...),
    district: str = Form(...)
):
    area_data = await get_area_code(city, district)
    if not area_data:
        return templates.TemplateResponse("recommendations.html", {
            "request": request,
            "category": category,
            "city": city,
            "district": district,
            "places": [],
            "error": "지역 정보를 찾을 수 없습니다."
        })

    area_code, sigungu_code = area_data
    places = await get_recommendations(category, area_code, sigungu_code)

    return templates.TemplateResponse("recommendations.html", {
        "request": request,
        "category": category,
        "city": city,
        "district": district,
        "places": places,
        "error": None
    })

# ▶ 4. (API) 시/도 리스트 가져오기
@app.get("/get_cities", response_class=JSONResponse)
async def get_cities():
    url = f"http://apis.data.go.kr/B551011/KorService1/areaCode1?serviceKey={SERVICE_KEY}"
    params = {
        "MobileOS": "ETC",
        "MobileApp": "AppTest",
        "_type": "json",
        "numOfRows": 100
    }

    response = requests.get(url, params=params)
    print("[DEBUG] 상태코드:", response.status_code)
    print("[DEBUG] 응답 텍스트:", response.text[:300])

    if response.status_code != 200:
        return JSONResponse(content={"error": "Failed to fetch cities"}, status_code=500)

    try:
        data = response.json()
    except Exception as e:
        print("[DEBUG] JSON 파싱 실패:", str(e))
        return JSONResponse(content={"error": "Invalid JSON response"}, status_code=500)

    items = data.get("response", {}).get("body", {}).get("items", {}).get("item", [])
    cities = [{"name": item["name"], "code": item["code"]} for item in items]
    return JSONResponse(content={"cities": cities})

# ▶ 5. (API) 선택한 시/도에 대한 시군구 리스트 가져오기
@app.get("/get_districts", response_class=JSONResponse)
async def get_districts(area_code: int):
    # 🔥 areaCode는 URL에 직접 포함
    url = f"http://apis.data.go.kr/B551011/KorService1/areaCode1?serviceKey={SERVICE_KEY}&areaCode={area_code}&MobileOS=ETC&MobileApp=AppTest&_type=json&numOfRows=100"

    response = requests.get(url)
    print("[DEBUG] /get_districts 응답코드:", response.status_code)
    print("[DEBUG] 응답 텍스트:", response.text[:300])

    if response.status_code != 200:
        return JSONResponse(content={"error": "Failed to fetch districts"}, status_code=500)

    try:
        data = response.json()
    except Exception as e:
        print("[DEBUG] JSON 파싱 실패:", str(e))
        return JSONResponse(content={"error": "Invalid JSON"}, status_code=500)

    items = data.get("response", {}).get("body", {}).get("items", {}).get("item", [])
    districts = [{"name": item["name"], "code": item["code"]} for item in items]
    return JSONResponse(content=districts)


# 🔹 (보조 함수) 시/도 + 시군구 코드를 얻는 함수
async def get_area_code(city: str, district: str):
    url = f"http://apis.data.go.kr/B551011/KorService1/areaCode1?serviceKey={SERVICE_KEY}"
    params = {
        "MobileOS": "ETC",
        "MobileApp": "AppTest",
        "_type": "json",
        "numOfRows": 100
    }

    response = requests.get(url, params=params)
    if response.status_code != 200:
        return None

    data = response.json()
    for item in data.get("response", {}).get("body", {}).get("items", {}).get("item", []):
        if item.get("name") == city:
            area_code = item.get("code")
            sub_url = f"http://apis.data.go.kr/B551011/KorService1/areaCode1?serviceKey={SERVICE_KEY}"
            sub_params = {
                "MobileOS": "ETC",
                "MobileApp": "AppTest",
                "_type": "json",
                "areaCode": area_code,
                "numOfRows": 100
            }
            sub_response = requests.get(sub_url, params=sub_params)
            if sub_response.status_code != 200:
                return None

            sub_data = sub_response.json()
            for sub_item in sub_data.get("response", {}).get("body", {}).get("items", {}).get("item", []):
                if sub_item.get("name") == district:
                    sigungu_code = sub_item.get("code")
                    return area_code, sigungu_code
    return None

# 🔹 (보조 함수) 추천 리스트 가져오기
async def get_recommendations(category: str, area_code: str, sigungu_code: str):
    content_type_id = CATEGORY_CODE_MAP.get(category)
    if not content_type_id:
        return []

    url = f"http://apis.data.go.kr/B551011/KorService1/areaBasedList1?serviceKey={SERVICE_KEY}"
    params = {
        "MobileOS": "ETC",
        "MobileApp": "AppTest",
        "_type": "json",
        "areaCode": area_code,
        "sigunguCode": sigungu_code,
        "contentTypeId": content_type_id,
        "numOfRows": 10
    }

    response = requests.get(url, params=params)
    if response.status_code != 200:
        return []

    data = response.json()
    items = data.get("response", {}).get("body", {}).get("items", {}).get("item", [])
    return items