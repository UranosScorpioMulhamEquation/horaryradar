from datetime import datetime, date, time
import itertools
import os
import base64
from typing import Dict, List, Tuple, Any, Optional

import geonamescache
import pandas as pd
import pytz
import streamlit as st
import swisseph as swe
from timezonefinder import TimezoneFinder

# ==========================================
# 0. تهيئة الصفحة ومسار ملفات الـ Ephemeris
# ==========================================
st.set_page_config(
    page_title="نظام التنجيم الساعي",
    layout="wide",
)

EPHE_PATH = "./ephe"
if not os.path.exists(EPHE_PATH):
    os.makedirs(EPHE_PATH)

swe.set_ephe_path(EPHE_PATH)

st.title(" 🔮 نظام التنجيم الساعي المتقدم (شامل الكويكيبات)")
st.markdown("مبني وفقاً للقواعد الكلاسيكية الدقيقة (خوان استاديا / أوليفيا باركلي) - برمجة الفلكي استرو رادار.")
st.markdown("---")

# ==========================================
# 1. خدمات البيانات الجغرافية والزمنية
# ==========================================
@st.cache_data
def load_geo_data() -> Tuple[geonamescache.GeonamesCache, Dict[str, str], List[str], Dict[str, List[Dict[str, Any]]]]:
    gc = geonamescache.GeonamesCache()
    countries = gc.get_countries()
    cities = gc.get_cities()

    country_map = {c["name"]: code for code, c in countries.items()}
    sorted_countries = sorted(list(country_map.keys()))

    cities_by_country: Dict[str, List[Dict[str, Any]]] = {}
    for c_code in country_map.values():
        c_cities = [city for city in cities.values() if city["countrycode"] == c_code]
        c_cities_sorted = sorted(c_cities, key=lambda x: x["population"], reverse=True)
        cities_by_country[c_code] = c_cities_sorted

    return gc, country_map, sorted_countries, cities_by_country

gc, country_map, country_list, cities_by_country = load_geo_data()

@st.cache_resource
def get_tz_finder() -> TimezoneFinder:
    return TimezoneFinder()

tf = get_tz_finder()

def get_utc_julian_day(date_obj: date, time_obj: time, tz_str: str) -> float:
    local_tz = pytz.timezone(tz_str)
    dt = datetime.combine(date_obj, time_obj)
    local_dt = local_tz.localize(dt)
    utc_dt = local_dt.astimezone(pytz.utc)
    return swe.julday(
        utc_dt.year,
        utc_dt.month,
        utc_dt.day,
        utc_dt.hour + utc_dt.minute / 60.0 + utc_dt.second / 3600.0,
    )

# ==========================================
# القواميس الفلكية التقليدية وأسئلة البيوت
# ==========================================
SIGN_NAMES = [
    "الحمل", "الثور", "الجوزاء", "السرطان", "الأسد", "العذراء",
    "الميزان", "العقرب", "القوس", "الجدي", "الدلو", "الحوت"
]

RULERS = {
    "الحمل": "المريخ", "الثور": "الزهرة", "الجوزاء": "عطارد",
    "السرطان": "القمر", "الأسد": "الشمس", "العذراء": "عطارد",
    "الميزان": "الزهرة", "العقرب": "المريخ", "القوس": "المشتري",
    "الجدي": "زحل", "الدلو": "زحل", "الحوت": "المشتري"
}

QUESTION_HOUSES = {
    "البيت 1: الشخص، البدايات، الصحة العامة، هل التغيير يناسبني؟": 1,
    "البيت 2: المال، الأصول، الأرباح، زيادة الراتب، أو استرداد شيء ضائع.": 2,
    "البيت 3: الرحلات القصيرة، الإخوة، الاتصالات، السياره، العقود البسيطة.": 3,
    "البيت 4: العقار، المنزل، الشقة، الأسرة، الأب، نهاية المسألة.": 4,
    "البيت 5: الأطفال، الحمل، المضاربات، الاستثمار، النجاح في الامتحانات.": 5,
    "البيت 6: العمل اليومي، الموظفون، الأمراض الحادة، الحيوانات الأليفة، الحميات.": 6,
    "البيت 7: الزواج، الشريك، العقود الكبرى، الخصوم، القضايا، نجاح الاستشارة.": 7,
    "البيت 8: الأموال المشتركة، الديون، الميراث، القروض، العمليات الجراحية.": 8,
    "البيت 9: السفر الطويل، الدراسات العليا، القضاء العالي، الشؤون الأجنبية.": 9,
    "البيت 10: المهنة، الترقية، السمعة الاجتماعية، السلطة، الأب/الرئيس.": 10,
    "البيت 11: الأصدقاء، المجموعات، الآمال والأماني، المنظمات.": 11,
    "البيت 12: السجون، المستشفيات، العزلة، الأعداء السريون، القيود الخفية.": 12,
}

# ==========================================
# الشريط الجانبي للإدخالات
# ==========================================
st.sidebar.header("⚙️ إعدادات السؤال، الزمان والمكان")

q_text = st.sidebar.selectbox(
    "اختر طبيعة السؤال (البيت الفلكي المرتبط):", list(QUESTION_HOUSES.keys())
)
target_house = QUESTION_HOUSES[q_text]

now_local = datetime.now()
q_date = st.sidebar.date_input("تاريخ طرح السؤال:", value=now_local.date())
q_time = st.sidebar.time_input("وقت طرح السؤال (المحلي):", value=now_local.time())

selected_country_name = st.sidebar.selectbox("اختر الدولة:", country_list, index=country_list.index("United Arab Emirates") if "United Arab Emirates" in country_list else 0)
country_code = country_map[selected_country_name]

country_cities = cities_by_country.get(country_code, [])
city_names = [c["name"] for c in country_cities]

if city_names:
    selected_city_name = st.sidebar.selectbox("اختر المدينة:", city_names)
    selected_city = next(c for c in country_cities if c["name"] == selected_city_name)
    lat = float(selected_city["latitude"])
    lon = float(selected_city["longitude"])
    tz_str = tf.timezone_at(lng=lon, lat=lat)
    if not tz_str:
        tz_str = "UTC"
else:
    lat = st.sidebar.number_input("خط العرض (Latitude):", value=25.2048, format="%.4f")
    lon = st.sidebar.number_input("خط الطول (Longitude):", value=55.2708, format="%.4f")
    tz_str = st.sidebar.text_input("المنطقة الزمنية (Timezone):", value="Asia/Dubai")

st.sidebar.write(f"🌍 الإحداثيات: {lat:.2f}, {lon:.2f} | التوقيت الزمني: {tz_str}")

def get_sign_and_deg(lon_deg):
    sign_idx = int(lon_deg / 30)
    deg_in_sign = lon_deg % 30
    sign_name = SIGN_NAMES[sign_idx % 12]
    return sign_name, deg_in_sign

if st.button("🚀 تحليل الخريطة الساعية واستخراج القرار"):
    try:
        jd = get_utc_julian_day(q_date, q_time, tz_str)
    except Exception as e:
        st.error(f"خطأ في حساب التوقيت والمنطقة الزمنية: {e}")
        st.stop()

    planets = {
        "الشمس": swe.SUN,
        "القمر": swe.MOON,
        "عطارد": swe.MERCURY,
        "الزهرة": swe.VENUS,
        "المريخ": swe.MARS,
        "المشتري": swe.JUPITER,
        "زحل": swe.SATURN,
    }

    planet_data = {}
    for p_name, p_id in planets.items():
        res, _ = swe.calc_ut(jd, p_id)
        lon_val = res[0]
        speed = res[3]
        sign, deg = get_sign_and_deg(lon_val)
        is_retro = speed < 0
        planet_data[p_name] = {
            "lon": lon_val,
            "sign": sign,
            "deg": deg,
            "retro": is_retro,
            "speed": speed,
        }

    houses_cusps, ascmc = swe.houses_ex(jd, lat, lon, b"R")
    asc_lon = houses_cusps[0]
    asc_sign, asc_deg = get_sign_and_deg(asc_lon)

    def find_house(p_lon):
        for i in range(12):
            c_start = houses_cusps[i]
            c_end = houses_cusps[(i + 1) % 12]
            if c_start < c_end:
                if c_start <= p_lon < c_end:
                    return i + 1
            else:
                if p_lon >= c_start or p_lon < c_end:
                    return i + 1
        return 1

    for p_name in planet_data:
        planet_data[p_name]["house"] = find_house(planet_data[p_name]["lon"])

    querent_ruler = RULERS[asc_sign]
    target_cusp_lon = houses_cusps[target_house - 1]
    target_sign, _ = get_sign_and_deg(target_cusp_lon)
    quesited_ruler = RULERS[target_sign]

    st.success("✨ تمت الحسابات الفلكية وتحويل التوقيت بنجاح عبر محرك Swiss Ephemeris!")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"### 🧑‍🦱 مؤشرات السائل (Querent)")
        st.write(f"- **الطالع:** {asc_sign} (الدرجة {asc_deg:.2f}°)")
        st.write(f"- **حاكم الطالع:** {querent_ruler} (في البرج: {planet_data[querent_ruler]['sign']}، البيت {planet_data[querent_ruler]['house']})")
        st.write(f"- **القمر (شاهد المسألة):** {planet_data['القمر']['sign']} ({planet_data['القمر']['deg']:.2f}°) في البيت {planet_data['القمر']['house']}")

    with col2:
        st.markdown(f"### 🎯 مؤشرات المسؤول عنه (Quesited - البيت {target_house})")
        st.write(f"- **رأس البيت {target_house}:** {target_sign}")
        st.write(f"- **حاكم البيت المستهدف:** {quesited_ruler} (في البرج: {planet_data[quesited_ruler]['sign']}، البيت {planet_data[quesited_ruler]['house']})")

    st.markdown("---")
    st.markdown("### 🛡️ تحليل الاتصالات المتقدم وفق القواعد الكلاسيكية")

    warnings = []
    obstacles = []

    moon_lon = planet_data["القمر"]["lon"]
    quesited_lon = planet_data[quesited_ruler]["lon"]
    querent_lon = planet_data[querent_ruler]["lon"]

    # دالة تفصيلية للاتصالات الكبرى (تثليث 120، تسداس 60، اقتران 0، تربيع 90، مقابلة 180)
    def check_aspect(lon1, lon2):
        diff = abs(lon1 - lon2) % 360
        if diff > 180:
            diff = 360 - diff
        
        if abs(diff - 120) <= 6.0:
            return True, "تثليث (Trine)", "positive"
        elif abs(diff - 60) <= 6.0:
            return True, "تسداس (Sextile)", "positive"
        elif abs(diff - 0) <= 8.0:
            return True, "اقتران (Conjunction)", "neutral"
        elif abs(diff - 90) <= 6.0:
            return True, "تربيع (Square)", "negative"
        elif abs(diff - 180) <= 6.0:
            return True, "مقابلة (Opposition)", "negative"
        return False, None, None

    # فحص علاقة حاكم البيت المستهدف مع القمر ومع حاكم الطالع
    has_moon_aspect, moon_asp_name, moon_asp_type = check_aspect(quesited_lon, moon_lon)
    has_querent_aspect, querent_asp_name, querent_asp_type = check_aspect(quesited_lon, querent_lon)

    # التحقق من تقنية "نقل النور" (Translation of Light) كلاسيكياً:
    # عندما ينفصل كوكب سريع عن أحدهما ليتصل بالآخر عبر وسيط، أو اتصال القمر كشاهد عام
    translation_detected = False
    for p_name, p_vals in planet_data.items():
        if p_name in [querent_ruler, quesited_ruler, "القمر"]:
            continue
        p_lon = p_vals["lon"]
        # هل الكوكب الوسيط يصنع اتصالاً مع الطرفين؟
        link1, _, t1 = check_aspect(p_lon, querent_lon)
        link2, _, t2 = check_aspect(p_lon, quesited_lon)
        if link1 and link2 and t1 == "positive" and t2 == "positive":
            translation_detected = True
            obstacles.append(f"تم رصد تقنية نقل/تجمع النور عبر الوسيط ({p_name}) لتسهيل الأمر.")

    # رصد المعوقات الكلاسيكية
    if planet_data[quesited_ruler]["retro"]:
        obstacles.append(f"حاكم المسؤول عنه ({quesited_ruler}) متراجع (يدل على تأخير أو مراجعة).")
    if planet_data["زحل"]["house"] in [1, 7, target_house]:
        obstacles.append("وجود زحل في الأوتاد أو بيت المسألة يفرض متطلبات أو تأخيراً صبوراً.")

    # ==========================================
    # المنطق النهائي المطور (دعم القبول مع مراعاة السلبيات الحقيقية)
    # ==========================================
    # المسألة تقبل (نعم) إذا وُجد اتصال إيجابي (تثليث/تسداس/اقتران) أو نقل نور فعال، ولم تكن هناك موانع قطعية مدمرة.
    is_positive = (moon_asp_type in ["positive", "neutral"] or querent_asp_type in ["positive", "neutral"] or translation_detected)
    is_severe_negative = (moon_asp_type == "negative" or querent_asp_type == "negative") and not translation_detected

    if is_severe_negative:
        final_verdict = "لا (تعذر اتمام المسألة بسبب اتصال سلبي قاطع: تربيع أو مقابلة)"
        detailed_explanation = (
            f"**تحليل الرفض:**<br>"
            f"رصد البرنامج اتصالاً سلبياً قاطعاً (تربيع أو مقابلة) دون وجود وسيط لنقل النور، مما يشير طبقاً للقواعد الكلاسيكية إلى عراقيل واضحة تمنع إتمام المسألة."
        )
    elif is_positive or has_moon_aspect or has_querent_aspect:
        final_verdict = "نعم (قبول المسألة)"
        if not obstacles:
            detailed_explanation = (
                f"**تحليل القبول الإيجابي:**<br>"
                f"1. **الاتصال الداعم:** توجد روابط زاوية إيجابية أو توافق مباشر بين دلالات البيت المستهدف ({target_house}) وحاكم الطالع أو القمر.<br>"
                f"2. **الخلاصة:** المسألة مقبولة وتتجه نحو النجاح."
            )
        else:
            detailed_explanation = (
                f"**تحليل القبول مع وجود معوقات جانبية:**<br>"
                f"1. **قبول المبدأ (نعم):** الاتجاه العام والمبدئي للمسألة إيجابي ويتم تحقيق الغاية.<br>"
                f"2. **الملاحظات والمعوقات:** {', '.join(obstacles)}.<br>"
                f"3. **الخلاصة:** الأمر يتم بنجاح ولكن مع بعض المتطلبات أو التأخير البسيط."
            )
    else:
        final_verdict = "غير واضح (بحاجة لدراسة يدوية دقيقة)"
        detailed_explanation = (
            f"**تحليل عدم الوضوح:**<br>"
            f"الروابط بين الدلائل غير مباشرة أو تحتاج لفحص دقيق لحالة النجوم الثابتة والاتصالات الصغرى."
        )

    st.subheader(f"النتيجة الحاسمة للمخرج: **{final_verdict}**")
    st.markdown("### الشرح الفلكي التفصيلي:")
    st.markdown(detailed_explanation, unsafe_allow_html=True)

    # ==========================================
    # زر طباعة / حفظ تقرير HTML
    # ==========================================
    st.markdown("---")
    
    html_report = f"""
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <title>تقرير التنجيم الساعي</title>
        <style>
            body {{ font-family: Tahoma, Arial, sans-serif; direction: rtl; text-align: right; padding: 20px; color: #333; }}
            h1, h2, h3 {{ color: #1e3d59; }}
            .box {{ background: #f5f7f8; padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #d1d5db; }}
            .verdict {{ font-size: 20px; font-weight: bold; color: #2e7d32; }}
        </style>
    </head>
    <body>
        <h1>🔮 تقرير نظام التنجيم الساعي الغربي</h1>
        <p><strong>تاريخ ووقت السؤال:</strong> {q_date} {q_time} ({tz_str})</p>
        <p><strong>نوع السؤال:</strong> {q_text}</p>
        
        <div class="box">
            <h2>مؤشرات الخريطة الأساسية</h2>
            <p><strong>الطالع:</strong> {asc_sign} (الدرجة {asc_deg:.2f}°)</p>
            <p><strong>حاكم الطالع:</strong> {querent_ruler}</p>
            <p><strong>حاكم البيت المستهدف ({target_house}):</strong> {quesited_ruler}</p>
            <p><strong>حالة القمر:</strong> {planet_data['القمر']['sign']} في البيت {planet_data['القمر']['house']}</p>
        </div>

        <div class="box">
            <h2>القرار النهائي والتحليل</h2>
            <p class="verdict">النتيجة: {final_verdict}</p>
            <h3>التفصيل الفلكي:</h3>
            <p>{detailed_explanation.replace('<br>', '<br>')}</p>
        </div>
        
        <footer style="margin-top: 30px; font-size: 12px; color: #777; text-align: center;">
            تم استخراج هذا التقرير تلقائياً عبر النظام المتقدم للتنجيم الساعي - استرو رادار.
        </footer>
    </body>
    </html>
    """

    b64 = base64.b64encode(html_report.encode("utf-8")).decode("utf-8")
    href = f'<a href="data:text/html;base64,{b64}" download="Horary_Report.html" style="display:inline-block; padding:10px 20px; background-color:#4CAF50; color:white; text-decoration:none; border-radius:5px; font-weight:bold;">📥 تحميل التقرير بصيغة HTML للطباعة</a>'
    st.markdown(href, unsafe_allow_html=True)
