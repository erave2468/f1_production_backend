from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Country


COUNTRIES = {
    "AU": ("Australia", "호주", "Australian"),
    "AT": ("Austria", "오스트리아", "Austrian"),
    "AZ": ("Azerbaijan", "아제르바이잔", "Azerbaijani"),
    "BH": ("Bahrain", "바레인", "Bahraini"),
    "BE": ("Belgium", "벨기에", "Belgian"),
    "BR": ("Brazil", "브라질", "Brazilian"),
    "CA": ("Canada", "캐나다", "Canadian"),
    "CN": ("China", "중국", "Chinese"),
    "DK": ("Denmark", "덴마크", "Danish"),
    "FI": ("Finland", "핀란드", "Finnish"),
    "FR": ("France", "프랑스", "French"),
    "DE": ("Germany", "독일", "German"),
    "HU": ("Hungary", "헝가리", "Hungarian"),
    "IN": ("India", "인도", "Indian"),
    "IT": ("Italy", "이탈리아", "Italian"),
    "JP": ("Japan", "일본", "Japanese"),
    "MY": ("Malaysia", "말레이시아", "Malaysian"),
    "MX": ("Mexico", "멕시코", "Mexican"),
    "MC": ("Monaco", "모나코", "Monegasque"),
    "NL": ("Netherlands", "네덜란드", "Dutch"),
    "NZ": ("New Zealand", "뉴질랜드", "New Zealander"),
    "PL": ("Poland", "폴란드", "Polish"),
    "PT": ("Portugal", "포르투갈", "Portuguese"),
    "QA": ("Qatar", "카타르", "Qatari"),
    "RU": ("Russia", "러시아", "Russian"),
    "SA": ("Saudi Arabia", "사우디아라비아", "Saudi Arabian"),
    "SG": ("Singapore", "싱가포르", "Singaporean"),
    "ZA": ("South Africa", "남아프리카공화국", "South African"),
    "KR": ("South Korea", "대한민국", "Korean"),
    "ES": ("Spain", "스페인", "Spanish"),
    "SE": ("Sweden", "스웨덴", "Swedish"),
    "CH": ("Switzerland", "스위스", "Swiss"),
    "TH": ("Thailand", "태국", "Thai"),
    "TR": ("Turkey", "튀르키예", "Turkish"),
    "AE": ("United Arab Emirates", "아랍에미리트", "Emirati"),
    "GB": ("United Kingdom", "영국", "British"),
    "US": ("United States", "미국", "American"),
    "AR": ("Argentina", "아르헨티나", "Argentine"),
}


ALIASES: dict[str, str] = {}

for code, (name_en, _, demonym) in COUNTRIES.items():
    ALIASES[code.lower()] = code
    ALIASES[name_en.lower()] = code
    ALIASES[demonym.lower()] = code


ALIASES.update(
    {
        "uk": "GB",
        "great britain": "GB",
        "england": "GB",

        "usa": "US",
        "united states of america": "US",

        "uae": "AE",

        "korea": "KR",
        "south korean": "KR",

        "russian": "RU",

        "argentinian": "AR",
    }
)


def country_code_from_text(
    value: str | None,
) -> str | None:
    if not value:
        return None

    key = value.strip().lower()

    return ALIASES.get(key)


def seed_countries(db: Session) -> None:
    for code, (
        name_en,
        name_ko,
        demonym_en,
    ) in COUNTRIES.items():

        country = db.get(Country, code)

        if country is None:
            country = Country(
                code=code,
                name_en=name_en,
                name_ko=name_ko,
                demonym_en=demonym_en,
            )

            db.add(country)

        else:
            country.name_en = name_en
            country.name_ko = name_ko
            country.demonym_en = demonym_en

    db.flush()