from datetime import datetime, date, time
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
    page_title="النظام المتقدم للتنجيم الساعي",
    layout="wide",
)

EPHE_PATH = "./ephe"
if not os.path.exists(EPHE_PATH):
    os.makedirs(EPHE_PATH)

swe.set_ephe_path(EPHE_PATH)

st.title("🔮 نظام التنجيم الساعي الغربي المتقدم (تطوير استرو رادار)")
st.markdown("مبني وفقاً للقواعد الكلاسيكية الدقيقة لوليام لي ونظام ريغومونتانوس مع محرك مرن لتقييم الموانع وتحليل النقاط.")
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
# القواميس الفلكية الشاملة
# ==========================================
SIGN_NAMES = [
    "الحمل", "الثور", "الجوزاء", "السرطان", "الأسد", "العذراء",
    "الميزان", "العقرب", "القوس", "الجدي", "الدلو", "الحوت"
]

SIGN_MODALITY = {
    "الحمل": "كاردينالي", "الثور": "ثابت", "الجوزاء": "متحرك",
    "السرطان": "كاردينالي", "الأسد": "ثابت", "العذراء": "متحرك",
    "الميزان": "كاردينالي", "العقرب": "ثابت", "القوس": "متحرك",
    "الجدي": "كاردينالي", "الدلو": "ثابت", "الحوت": "متحرك"
}

RULERS = {
    "الحمل": "المريخ", "الثور": "الزهرة", "الجوزاء": "عطارد",
    "السرطان": "القمر", "الأسد": "الشمس", "العذراء": "عطارد",
    "الميزان": "الزهرة", "العقرب": "المريخ", "القوس": "المشتري",
    "الجدي": "زحل", "الدلو": "زحل", "الحوت": "المشتري"
}

QUESTION_HOUSES = {
    "البيت 1: الشخص، البدايات، الصحة العامة، هل التغيير يناسبني؟": 1,
    "البيت 2: المال، الأصول، الأرباح، زيادة الراتب، أو استرداد شيء ضائع.": 2,
    "البيت 3: الرحلات القصيرة، الإخوة، الاتصالات، السيارة، العقود البسيطة.": 3,
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
# الشريط الجانبي للإدخالات مع تثبيت الحالة
# ==========================================
st.sidebar.header("⚙️ إعدادات السؤال، الزمان والمكان")

q_text = st.sidebar.selectbox(
    "اختر طبيعة السؤال (البيت الفلكي المرتبط):", list(QUESTION_HOUSES.keys()), key="q_text_select"
)
target_house = QUESTION_HOUSES[q_text]

if "q_date_val" not in st.session_state:
    st.session_state.q_date_val = datetime.now().date()
if "q_time_val" not in st.session_state:
    st.session_state.q_time_val = datetime.now().time()

q_date = st.sidebar.date_input("تاريخ طرح السؤال:", key="q_date_val")
q_time = st.sidebar.time_input("وقت طرح السؤال (المحلي):", key="q_time_val")

default_country_idx = country_list.index("United Arab Emirates") if "United Arab Emirates" in country_list else 0
selected_country_name = st.sidebar.selectbox("اختر الدولة:", country_list, index=default_country_idx, key="country_select")
country_code = country_map[selected_country_name]

country_cities = cities_by_country.get(country_code, [])
city_names = [c["name"] for c in country_cities]

if city_names:
    selected_city_name = st.sidebar.selectbox("اختر المدينة:", city_names, key="city_select")
    selected_city = next(c for c in country_cities if c["name"] == selected_city_name)
    lat = float(selected_city["latitude"])
    lon = float(selected_city["longitude"])
    tz_str = tf.timezone_at(lng=lon, lat=lat) or "UTC"
else:
    lat = st.sidebar.number_input("خط العرض (Latitude):", value=25.2048, format="%.4f", key="lat_input")
    lon = st.sidebar.number_input("خط الطول (Longitude):", value=55.2708, format="%.4f", key="lon_input")
    tz_str = st.sidebar.text_input("المنطقة الزمنية (Timezone):", value="Asia/Dubai", key="tz_input")

st.sidebar.write(f"🌍 الإحداثيات: {lat:.2f}, {lon:.2f} | التوقيت الزمني: {tz_str}")

def get_sign_and_deg(lon_deg):
    lon_deg = lon_deg % 360
    sign_idx = int(lon_deg / 30)
    deg_in_sign = lon_deg % 30
    sign_name = SIGN_NAMES[sign_idx % 12]
    return sign_name, deg_in_sign

if st.button("🚀 تحليل الخريطة الساعية واستخراج القرار", type="primary"):
    try:
        jd = get_utc_julian_day(q_date, q_time, tz_str)
    except Exception as e:
        st.error(f"خطأ في حساب التوقيت والمنطقة الزمنية: {e}")
        st.stop()

    # القاموس الفلكي الشامل (الكواكب التقليدية + العقد والكويكبات)
    planets = {
        "الشمس": swe.SUN,
        "القمر": swe.MOON,
        "عطارد": swe.MERCURY,
        "الزهرة": swe.VENUS,
        "المريخ": swe.MARS,
        "المشتري": swe.JUPITER,
        "زحل": swe.SATURN,
        "الراس (الشمالية)": swe.MEAN_NODE,
        "تشيرون (Chiron)": swe.CHIRON,
    }

    planet_data = {}
    for p_name, p_id in planets.items():
        res, _ = swe.calc_ut(jd, p_id)
        lon_val = res[0]
        speed = res[3]
        sign, deg = get_sign_and_deg(lon_val)
        planet_data[p_name] = {
            "lon": lon_val,
            "sign": sign,
            "deg": deg,
            "retro": speed < 0,
            "speed": speed,
        }

    # حساب دقيق للعقدة الجنوبية (الكيتو) المعاكسة تماماً للعقدة الشمالية
    ketu_lon = (planet_data["الراس (الشمالية)"]["lon"] + 180.0) % 360
    ketu_sign, ketu_deg = get_sign_and_deg(ketu_lon)
    planet_data["الكيتو (الجنوبية)"] = {
        "lon": ketu_lon,
        "sign": ketu_sign,
        "deg": ketu_deg,
        "retro": planet_data["الراس (الشمالية)"]["retro"],
        "speed": planet_data["الراس (الشمالية)"]["speed"],
    }

    # حساب البيوت بنظام ريغومونتانوس (Regiomontanus)
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

    st.success(f"✨ تمت الحسابات للوقت ({q_time}) وتاريخ ({q_date}) بنجاح عبر محرك Swiss Ephemeris بنظام ريغومونتانوس!")

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
    st.markdown("### 🛡️ التحذيرات والكراهات الفلكية (Gatekeepers & Cautions)")

    warnings_list = []

    # 1. فحص درجات الطالع الحرجة
    if asc_deg < 3.0:
        warnings_list.append("⚠️ **تحذير طالع مبكر:** درجة الطالع أقل من 3 درجات (الموضوع في بدايته ولم ينضج بعد / سابق لأوانه).")
    elif asc_deg > 27.0:
        warnings_list.append("⚠️ **تحذير طالع متأخر:** درجة الطالع أكثر من 27 درجة (الموضوع متأخر جداً أو الوضع حتمي ولا رجوع فيه).")

    # 2. فحص خلو المسار للقمر (Void of Course) بمرونة
    moon_lon = planet_data["القمر"]["lon"]
    moon_deg_in_sign = planet_data["القمر"]["deg"]
    degrees_left = 30.0 - moon_deg_in_sign
    
    # فحص بسيط ومنطقي: إذا كانت الدرجات المتبقية صغيرة جداً (< 2 درجة) ولم يصنع اتصالاً قريباً
    moon_voc = False
    if degrees_left < 2.0:
        moon_voc = True
        warnings_list.append("⚠️ **تنبيه فلكي:** القمر في أواخر برجه (خالي السير تقريباً / Void of Course) ودلالة على بطء أو تعذر تحقق النتائج السريعة.")

    # 3. فحص وجود زحل في الأوتاد الحرجة
    saturn_house = planet_data["زحل"]["house"]
    if saturn_house in [1, 7, target_house]:
        warnings_list.append(f"⚠️ **وجود نحس (زحل):** زحل يترصد في البيت {saturn_house} مما يفرض قيوداً أو تأخيراً أو عرقلة تتطلب حذراً شديداً.")

    if warnings_list:
        for w in warnings_list:
            st.warning(w)
    else:
        st.info("✅ الخريطة خالية من العوائق الكلاسيكية الكبرى (الطالع في المدى الطبيعي ولا وجود لزحل في الأوتاد الحساسة).")

    st.markdown("---")
    st.markdown("### 📊 محرك النقاط ومصفوفة القرار النهائي")

    def check_aspect(p1_data, p2_data):
        lon1 = p1_data["lon"]
        lon2 = p2_data["lon"]

        diff = abs(lon1 - lon2) % 360
        if diff > 180:
            diff = 360 - diff

        aspects = [
            (0, "اقتران (Conjunction)", "neutral", 8.0),
            (60, "تسديس (Sextile)", "positive", 6.0),
            (90, "تربيع (Square)", "negative", 6.0),
            (120, "تثليث (Trine)", "positive", 6.0),
            (180, "مقابلة (Opposition)", "negative", 6.0),
        ]

        for target_angle, asp_name, asp_type, max_orb in aspects:
            if abs(diff - target_angle) <= max_orb:
                orb = abs(diff - target_angle)
                return True, asp_name, asp_type, orb, "تقاربي (Applying)"
        
        return False, None, None, 0.0, None

    quesited_pdata = planet_data[quesited_ruler]
    querent_pdata = planet_data[querent_ruler]
    moon_pdata = planet_data["القمر"]

    has_moon_asp, moon_asp_name, moon_asp_type, moon_orb, moon_state = check_aspect(moon_pdata, quesited_pdata)
    has_querent_asp, querent_asp_name, querent_asp_type, querent_orb, querent_state = check_aspect(querent_pdata, quesited_pdata)

    score = 0
    score_details = []

    if has_moon_asp:
        if moon_asp_type == "positive":
            score += 4
            score_details.append(f"اتصال إيجابي بين القمر وحاكم المسؤول عنه ({moon_asp_name}): +4 نقاط")
        elif moon_asp_type == "negative":
            score -= 4
            score_details.append(f"اتصال سلبي بين القمر وحاكم المسؤول عنه ({moon_asp_name}): -4 نقاط")
        elif moon_asp_type == "neutral":
            score += 2
            score_details.append(f"اقتران بين القمر وحاكم المسؤول عنه: +2 نقاط")

    if has_querent_asp:
        if querent_asp_type == "positive":
            score += 4
            score_details.append(f"اتصال إيجابي بين حاكم الطالع وحاكم المسؤول عنه ({querent_asp_name}): +4 نقاط")
        elif querent_asp_type == "negative":
            score -= 4
            score_details.append(f"اتصال سلبي بين حاكم الطالع وحاكم المسؤول عنه ({querent_asp_name}): -4 نقاط")
        elif querent_asp_type == "neutral":
            score += 2
            score_details.append(f"اقتران بين حاكم الطالع وحاكم المسؤول عنه: +2 نقاط")

    sun_lon = planet_data["الشمس"]["lon"]
    for p_name in [querent_ruler, quesited_ruler]:
        if abs(planet_data[p_name]["lon"] - sun_lon) <= 8.5:
            score -= 4
            score_details.append(f"الكوكب ({p_name}) محترق بالشمس (Combustion): -4 نقاط")

    if planet_data[quesited_ruler]["retro"]:
        if target_house == 2:
            score += 3
            score_details.append(f"تراجع حاكم البيت الثاني للسؤال عن مال أو شيء ضائع: +3 نقاط")
        else:
            score -= 2
            score_details.append(f"حاكم المسؤول عنه ({quesited_ruler}) متراجع: -2 نقطة")

    querent_sign = planet_data[querent_ruler]["sign"]
    quesited_sign = planet_data[quesited_ruler]["sign"]
    if RULERS.get(querent_sign) == quesited_ruler and RULERS.get(quesited_sign) == querent_ruler:
        score += 5
        score_details.append("وجود استقبال متبادل بين حاكم الطالع وحاكم البيت المستهدف (Mutual Reception): +5 نقاط")

    def calculate_timing(house_num, sign_name, orb_deg):
        if house_num in [1, 4, 7, 10]:
            h_type = "زاوية"
        elif house_num in [2, 5, 8, 11]:
            h_type = "تابعة"
        else:
            h_type = "هابطة"

        mod = SIGN_MODALITY.get(sign_name, "كاردينالي")

        table = {
            "زاوية": {"كاردينالي": "أيام", "متحرك": "أسابيع", "ثابت": "أشهر"},
            "تابعة": {"كاردينالي": "أسابيع", "متحرك": "أشهر", "ثابت": "سنين"},
            "هابطة": {"كاردينالي": "أشهر", "متحرك": "سنين", "ثابت": "وقت غير محدد"}
        }

        unit = table.get(h_type, {}).get(mod, "أيام")
        if unit == "وقت غير محدد":
            return "وقت غير محدد"
        return f"حوالي {orb_deg:.1f} {unit}"

    estimated_time = "غير محدد"
    if has_moon_asp:
        estimated_time = calculate_timing(planet_data["القمر"]["house"], planet_data["القمر"]["sign"], moon_orb)
    elif has_querent_asp:
        estimated_time = calculate_timing(planet_data[querent_ruler]["house"], planet_data[querent_ruler]["sign"], querent_orb)

    # مصفوفة القرار النهائي بناءً على النقاط الكلية
    if score >= 4:
        final_verdict = "نعم (Yes - قبول تام وتحقق المسألة)"
        verdict_color = "green"
    elif score <= -2:
        final_verdict = "لا (No - تعذر إتمام المسألة أو رفضها)"
        verdict_color = "red"
    else:
        final_verdict = "غير واضح / معلق (Unclear - تتطلب مراجعة أو وجود عراقيل)"
        verdict_color = "orange"

    st.markdown(f"### 🎯 المجموع الكلي للنقاط: **{score} نقطة**")
    st.markdown(f"### النتيجة الحاسمة: <span style='color:{verdict_color}; font-size:24px;'>**{final_verdict}**</span>", unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### 📋 تفصيل حساب النقاط والمؤشرات الفلكية:")
    if score_details:
        for detail in score_details:
            st.write(f"- {detail}")
    else:
        st.write("- لم يتم تسجيل ارتباطات اتصالات كبرى مباشرة بين الأدلة الأساسية حالياً.")

    st.write(f"- **الوقت المتوقع لتحقق المسألة:** {estimated_time}")

    # ==========================================
    # تقرير HTML للطباعة
    # ==========================================
    st.markdown("---")

    html_report = f"""
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <title>تقرير التنجيم الساعي المتقدم</title>
        <style>
            body {{ font-family: Tahoma, Arial, sans-serif; direction: rtl; text-align: right; padding: 20px; color: #333; }}
            h1, h2, h3 {{ color: #1e3d59; }}
            .box {{ background: #f5f7f8; padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #d1d5db; }}
            .verdict {{ font-size: 22px; font-weight: bold; color: {verdict_color}; }}
        </style>
    </head>
    <body>
        <h1>🔮 تقرير نظام التنجيم الساعي الغربي المتقدم</h1>
        <p><strong>تاريخ ووقت السؤال:</strong> {q_date} {q_time} ({tz_str})</p>
        <p><strong>نوع السؤال:</strong> {q_text}</p>

        <div class="box">
            <h2>مؤشرات الخريطة الأساسية والاتصالات</h2>
            <p><strong>الطالع:</strong> {asc_sign} (الدرجة {asc_deg:.2f}°)</p>
            <p><strong>حاكم الطالع:</strong> {querent_ruler}</p>
            <p><strong>حاكم البيت المستهدف ({target_house}):</strong> {quesited_ruler}</p>
            <p><strong>حالة القمر:</strong> {planet_data['القمر']['sign']} في البيت {planet_data['القمر']['house']}</p>
        </div>

        <div class="box">
            <h2>القرار النهائي والنقاط</h2>
            <p class="verdict">النتيجة: {final_verdict} (المجموع: {score} نقطة)</p>
            <p><strong>الوقت المتوقع للتحقق:</strong> {estimated_time}</p>
            <h3>تفاصيل محرك النقاط:</h3>
            <ul>
                {"".join([f"<li>{d}</li>" for d in score_details]) if score_details else "<li>لا توجد اتصالات كبرى مسجلة</li>"}
            </ul>
        </div>

        <footer style="margin-top: 30px; font-size: 12px; color: #777; text-align: center;">
            جميع الحقوق محفوظة للنظام الفلكي (تطوير استرو رادار).
        </footer>
    </body>
    </html>
    """

    b64 = base64.b64encode(html_report.encode("utf-8")).decode("utf-8")
    href = f'<a href="data:text/html;base64,{b64}" download="Advanced_Horary_Report.html" style="display:inline-block; padding:10px 20px; background-color:#4CAF50; color:white; text-decoration:none; border-radius:5px; font-weight:bold;">📥 تحميل التقرير الشامل بصيغة HTML للطباعة</a>'
    st.markdown(href, unsafe_allow_html=True)
