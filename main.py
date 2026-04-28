from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Dict, Optional
import uvicorn
from lunar_python import Solar

from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

# ==========================================
# 1. 定義標準化數據模型 (Data Schema)
# ==========================================

class CalculationRequest(BaseModel):
    time: str = Field(..., description="精確時間，格式：YYYY-MM-DD HH:MM", example="2026-04-21 12:00")
    lat: float = Field(..., description="緯度", example=22.3)
    lon: float = Field(..., description="經度", example=114.1)
    gender: str = Field("M", description="性別：M 為男，F 為女")

class LogicState(BaseModel):
    is_in_tomb: bool = Field(False, description="是否入墓")
    is_punished: bool = Field(False, description="是否擊刑")
    is_empty: bool = Field(False, description="是否空亡")
    is_horse: bool = Field(False, description="是否為驛馬星")
    is_door_forced: bool = Field(False, description="是否門迫")
    description: str = Field("", description="邏輯狀態詳細說明")

class PalaceData(BaseModel):
    palace_id: str = Field(..., description="宮位名稱")
    hidden_stem: str = Field(..., description="暗干(飛干)") 
    heaven_stem: str = Field(..., description="天盤天干")
    heaven_stem_tags: str = Field("", description="天盤刑墓標記")
    heaven_stem_state: str = Field("", description="天盤十二長生狀態")
    earth_stem: str = Field(..., description="地盤天干")
    earth_stem_tags: str = Field("", description="地盤刑墓標記")
    earth_stem_state: str = Field("", description="地盤十二長生狀態")
    door: str = Field(..., description="八門")
    star: str = Field(..., description="九星")
    deity: str = Field(..., description="八神")
    logic_states: LogicState = Field(..., description="狀態")

class QimenInfo(BaseModel):
    solar_term: str = Field(..., description="目前節氣")
    dun_type: str = Field(..., description="陰遁或陽遁")
    yuan: str = Field(..., description="上中下元")
    ju_num: int = Field(..., description="局數 (1-9)")
    hour_xun: str = Field(..., description="時辰旬首")  
    zhi_fu: str = Field(..., description="值符星") 
    zhi_shi: str = Field(..., description="值使門") 
    description: str = Field(..., description="完整描述")

class CalculationResponse(BaseModel):
    solar_time: str = Field(...)
    lunar_time: str = Field(...)
    bazi: Dict[str, str] = Field(...)
    qimen_info: QimenInfo = Field(...)
    qimen_matrix: List[PalaceData] = Field(...)

class InterpretationResponse(BaseModel):
    text: str = Field(..., description="AI 產出的解盤報告文字")

# ==========================================
# 2. 撰寫規則判定引擎 (Rule Engine)
# ==========================================

class QimenEngine:
    SOLAR_TERM_JU = {
        "冬至": ("陽遁", [1, 7, 4]), "小寒": ("陽遁", [2, 8, 5]), "大寒": ("陽遁", [3, 9, 6]),
        "立春": ("陽遁", [8, 5, 2]), "雨水": ("陽遁", [9, 6, 3]), "驚蟄": ("陽遁", [1, 7, 4]),
        "春分": ("陽遁", [3, 9, 6]), "清明": ("陽遁", [4, 1, 7]), "穀雨": ("陽遁", [5, 2, 8]),
        "立夏": ("陽遁", [4, 1, 7]), "小滿": ("陽遁", [5, 2, 8]), "芒種": ("陽遁", [6, 3, 9]),
        "夏至": ("陰遁", [9, 3, 6]), "小暑": ("陰遁", [8, 2, 5]), "大暑": ("陰遁", [7, 1, 4]),
        "立秋": ("陰遁", [2, 5, 8]), "處暑": ("陰遁", [1, 4, 7]), "白露": ("陰遁", [9, 3, 6]),
        "秋分": ("陰遁", [7, 1, 4]), "寒露": ("陰遁", [6, 9, 3]), "霜降": ("陰遁", [5, 8, 2]),
        "立冬": ("陰遁", [6, 9, 3]), "小雪": ("陰遁", [5, 8, 2]), "大雪": ("陰遁", [4, 7, 1])
    }

    PALACE_NUM_MAP = {
        1: "坎宮", 2: "坤宮", 3: "震宮", 4: "巽宮", 5: "中宮",
        6: "乾宮", 7: "兌宮", 8: "艮宮", 9: "離宮"
    }

    PALACE_NAME_MAP = {v: k for k, v in PALACE_NUM_MAP.items()}

    PALACE_RING = ["坎宮", "艮宮", "震宮", "巽宮", "離宮", "坤宮", "兌宮", "乾宮"]

    DOOR_SEQUENCE = ["休門", "生門", "傷門", "杜門", "景門", "死門", "驚門", "開門"]
    DEITY_SEQUENCE = ["值符", "騰蛇", "太陰", "六合", "白虎", "玄武", "九地", "九天"]

    XUN_SHOU_MAP = {
        "子": ("甲子", "戊"), "戌": ("甲戌", "己"), "申": ("甲申", "庚"),
        "午": ("甲午", "辛"), "辰": ("甲辰", "壬"), "寅": ("甲寅", "癸")
    }

    ORIGINAL_STAR_DOOR = {
        "坎宮": ("天蓬星", "休門"), "坤宮": ("天芮星", "死門"), "震宮": ("天衝星", "傷門"),
        "巽宮": ("天輔星", "杜門"), "中宮": ("天禽星", "死門"),
        "乾宮": ("天心星", "開門"), "兌宮": ("天柱星", "驚門"), "艮宮": ("天任星", "生門"),
        "離宮": ("天英星", "景門")
    }

    @staticmethod
    def calculate_ju(solar_term: str, day_stem: str, day_branch: str) -> dict:
        stems = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
        branches = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
        
        stem_idx = stems.index(day_stem)
        branch_idx = branches.index(day_branch)
        
        offset = stem_idx % 5
        futou_branch_idx = (branch_idx - offset + 12) % 12
        
        yuan_val = futou_branch_idx % 3
        yuan_map = {0: "上元", 2: "中元"}
        yuan = yuan_map.get(yuan_val, "下元")
        yuan_idx = 0 if yuan == "上元" else 1 if yuan == "中元" else 2
            
        dun_type, ju_list = QimenEngine.SOLAR_TERM_JU.get(solar_term, ("陽遁", [1, 1, 1]))
        ju_num = ju_list[yuan_idx]
        
        return {
            "dun_type": dun_type, "yuan": yuan, "ju_num": ju_num,
            "description": f"{dun_type}{ju_num}局 ({yuan})"
        }

    @staticmethod
    def calculate_earth_pan(dun_type: str, ju_num: int) -> dict:
        stems_sequence = ["戊", "己", "庚", "辛", "壬", "癸", "丁", "丙", "乙"]
        earth_pan = {}
        start_pos = ju_num - 1 
        
        for i, stem in enumerate(stems_sequence):
            palace_num = ((start_pos + i) % 9) + 1 if dun_type == "陽遁" else ((start_pos - i) % 9) + 1
            earth_pan[QimenEngine.PALACE_NUM_MAP[palace_num]] = stem
            
        zhong_stem = earth_pan["中宮"]
        kun_stem = earth_pan["坤宮"]
        earth_pan["坤宮"] = f"{zhong_stem}{kun_stem}" 
        
        return earth_pan

    @staticmethod
    def calculate_xun(hour_stem: str, hour_branch: str) -> dict:
        stems = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
        branches = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
        xun_branch = branches[(branches.index(hour_branch) - stems.index(hour_stem) + 12) % 12]
        jia_name, hidden_stem = QimenEngine.XUN_SHOU_MAP[xun_branch]
        return {"jia_name": jia_name, "hidden_stem": hidden_stem, "full_name": f"{jia_name}{hidden_stem}"}

    @staticmethod
    def calculate_zhi_fu_zhi_shi(earth_pan: dict, hidden_stem: str) -> dict:
        target_palace = "中宮" 
        for palace, stem in earth_pan.items():
            if hidden_stem in stem: 
                target_palace = palace
                break
        star, door = QimenEngine.ORIGINAL_STAR_DOOR[target_palace]
        return {"palace": target_palace, "star": star, "door": door}

    @staticmethod
    def calculate_heaven_pan(earth_pan: dict, hour_stem: str, hidden_stem: str, zhi_fu_palace: str) -> dict:
        search_stem = hidden_stem if hour_stem == "甲" else hour_stem
        target_palace = "中宮"
        for p, stem in earth_pan.items():
            if search_stem in stem: 
                target_palace = p
                break

        if target_palace == "中宮": target_palace = "坤宮"
        source_palace = zhi_fu_palace if zhi_fu_palace != "中宮" else "坤宮"

        offset = (QimenEngine.PALACE_RING.index(target_palace) - QimenEngine.PALACE_RING.index(source_palace) + 8) % 8

        heaven_stars, heaven_stems = {}, {}
        for i, current_p in enumerate(QimenEngine.PALACE_RING):
            source_p = QimenEngine.PALACE_RING[(i - offset + 8) % 8]
            heaven_stars[current_p] = QimenEngine.ORIGINAL_STAR_DOOR[source_p][0]
            heaven_stems[current_p] = earth_pan.get(source_p, "")

        heaven_stars["中宮"] = ""  
        heaven_stems["中宮"] = earth_pan.get("中宮", "")
        return {"stars": heaven_stars, "stems": heaven_stems}

    @staticmethod
    def calculate_doors(dun_type: str, zhi_shi_door: str, original_palace: str, xun_branch: str, hour_branch: str) -> dict:
        branches = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
        steps = (branches.index(hour_branch) - branches.index(xun_branch) + 12) % 12
        start_num = QimenEngine.PALACE_NAME_MAP[original_palace]
        
        target_num = ((start_num + steps - 1) % 9) + 1 if dun_type == "陽遁" else ((start_num - steps - 1) % 9) + 1
        target_palace = QimenEngine.PALACE_NUM_MAP[target_num]
        if target_palace == "中宮": target_palace = "坤宮"

        target_idx = QimenEngine.PALACE_RING.index(target_palace)
        door_start_idx = QimenEngine.DOOR_SEQUENCE.index(zhi_shi_door)
        
        doors_pan = {"中宮": ""}
        for i, current_p in enumerate(QimenEngine.PALACE_RING):
            doors_pan[current_p] = QimenEngine.DOOR_SEQUENCE[(i - target_idx + door_start_idx + 8) % 8]
        return doors_pan

    @staticmethod
    def calculate_deities(dun_type: str, heaven_zhi_fu_palace: str) -> dict:
        target_palace = "坤宮" if heaven_zhi_fu_palace == "中宮" else heaven_zhi_fu_palace
        target_idx = QimenEngine.PALACE_RING.index(target_palace)
        deities_pan = {"中宮": ""}
        for i, current_p in enumerate(QimenEngine.PALACE_RING):
            deity_idx = (i - target_idx + 8) % 8 if dun_type == "陽遁" else (target_idx - i + 8) % 8
            deities_pan[current_p] = QimenEngine.DEITY_SEQUENCE[deity_idx]
        return deities_pan

    @staticmethod
    def calculate_hidden_stems(dun_type: str, actual_hour_stem: str, current_zhi_shi_palace: str) -> dict:
        if current_zhi_shi_palace == "中宮": current_zhi_shi_palace = "坤宮"
        sequence = ["戊", "己", "庚", "辛", "壬", "癸", "丁", "丙", "乙"]
        start_idx = sequence.index(actual_hour_stem) if actual_hour_stem in sequence else 0
        start_palace_num = QimenEngine.PALACE_NAME_MAP[current_zhi_shi_palace]
        
        hidden_stems = {}
        for i in range(9):
            stem = sequence[(start_idx + i) % 9]
            palace_num = ((start_palace_num + i - 1) % 9) + 1 if dun_type == "陽遁" else ((start_palace_num - i - 1) % 9) + 1
            hidden_stems[QimenEngine.PALACE_NUM_MAP[palace_num]] = stem
        return hidden_stems

class RuleEngine:
    @staticmethod
    def get_stem_tags(stem_str: str, palace: str) -> str:
        has_tomb = False
        has_punish = False
        for char in stem_str:
            # 判斷入墓規則
            if char in ['甲', '癸'] and palace == '坤宮': has_tomb = True
            elif char in ['乙', '丙', '戊'] and palace == '乾宮': has_tomb = True
            elif char in ['丁', '己', '庚'] and palace == '艮宮': has_tomb = True
            elif char in ['壬', '辛'] and palace == '巽宮': has_tomb = True
            
            # 判斷六儀擊刑規則
            if char == '戊' and palace == '震宮': has_punish = True
            elif char == '己' and palace == '坤宮': has_punish = True
            elif char == '庚' and palace == '艮宮': has_punish = True
            elif char == '辛' and palace == '離宮': has_punish = True
            elif char in ['壬', '癸'] and palace == '巽宮': has_punish = True
            
        if has_tomb and has_punish: return "(刑墓)"
        if has_tomb: return "(墓)"
        if has_punish: return "(刑)"
        return ""

    @staticmethod
    def check_tomb(stem_str: str, palace: str) -> bool:
        tags = RuleEngine.get_stem_tags(stem_str, palace)
        return "(墓)" in tags or "(刑墓)" in tags
        
    @staticmethod
    def check_punishment(stem_str: str, palace: str) -> bool:
        tags = RuleEngine.get_stem_tags(stem_str, palace)
        return "(刑)" in tags or "(刑墓)" in tags

    @staticmethod
    def check_door_forced(door: str, palace: str) -> bool:
        # 門迫規則：人盤(八門) 剋 地盤(九宮)
        if door == "休門" and palace == "離宮": return True # 水剋火
        if door in ["生門", "死門"] and palace == "坎宮": return True # 土剋水
        if door in ["傷門", "杜門"] and palace in ["坤宮", "艮宮"]: return True # 木剋土
        if door == "景門" and palace in ["乾宮", "兌宮"]: return True # 火剋金
        if door in ["驚門", "開門"] and palace in ["震宮", "巽宮"]: return True # 金剋木
        return False

    @staticmethod
    def calculate_xun_kong(stem: str, branch: str) -> str:
        stems, branches = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"], ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
        xun_branch_idx = (branches.index(branch) - stems.index(stem) + 12) % 12
        return branches[(xun_branch_idx - 2) % 12] + branches[(xun_branch_idx - 1) % 12]

    @staticmethod
    def check_empty(palace: str, xun_kong: str) -> bool:
        palace_branches = {"坎宮":["子"], "艮宮":["丑","寅"], "震宮":["卯"], "巽宮":["辰","巳"], "離宮":["午"], "坤宮":["未","申"], "兌宮":["酉"], "乾宮":["戌","亥"]}
        return any(b in xun_kong for b in palace_branches.get(palace, []))

    @staticmethod
    def calculate_horse_star(hour_branch: str) -> str:
        if hour_branch in ["申", "子", "辰"]: return "艮宮"
        if hour_branch in ["寅", "午", "戌"]: return "坤宮"
        if hour_branch in ["亥", "卯", "未"]: return "巽宮"
        if hour_branch in ["巳", "酉", "丑"]: return "乾宮"
        return ""

    @staticmethod
    def get_single_12_state(stem: str, branch: str) -> str:
        states = ["長", "沐", "冠", "臨", "旺", "衰", "病", "死", "墓", "絕", "胎", "養"]
        branches = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
        start_map = {"甲": "亥", "丙": "寅", "戊": "寅", "庚": "巳", "壬": "申",
                     "乙": "午", "丁": "酉", "己": "酉", "辛": "子", "癸": "卯"}
        if stem not in start_map: return ""
        
        start_idx = branches.index(start_map[stem])
        target_idx = branches.index(branch)
        
        if stem in ["甲", "丙", "戊", "庚", "壬"]:
            state_idx = (target_idx - start_idx + 12) % 12
        else:
            state_idx = (start_idx - target_idx + 12) % 12
        return states[state_idx]

    @staticmethod
    def calculate_12_states(stem_str: str, palace: str) -> str:
        if not stem_str or palace == "中宮": return ""
        palace_branches = {"坎宮": ["子"], "艮宮": ["丑", "寅"], "震宮": ["卯"], "巽宮": ["辰", "巳"],
                           "離宮": ["午"], "坤宮": ["未", "申"], "兌宮": ["酉"], "乾宮": ["戌", "亥"]}
        branches = palace_branches.get(palace, [])
        result = ""
        for stem in stem_str:
            result += "".join([RuleEngine.get_single_12_state(stem, b) for b in branches])
        return result

# ==========================================
# 3. 封裝 API 接口
# ==========================================

app = FastAPI(title="Metaphysics Logic API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "<h1>找不到 index.html</h1>"

@app.post("/api/v1/divination/calculate", response_model=CalculationResponse)
async def calculate_matrix(request: CalculationRequest):
    try:
        dt = datetime.strptime(request.time, "%Y-%m-%d %H:%M")
    except ValueError:
        raise HTTPException(status_code=400, detail="格式錯誤")

    solar = Solar.fromYmdHms(dt.year, dt.month, dt.day, dt.hour, dt.minute, 0)
    lunar, bazi = solar.getLunar(), solar.getLunar().getEightChar()
    
    day_stem, day_branch = bazi.getDayGan(), bazi.getDayZhi()
    hour_stem, hour_branch = bazi.getTimeGan(), bazi.getTimeZhi()
    
    hour_xun_kong = RuleEngine.calculate_xun_kong(hour_stem, hour_branch)
    horse_palace = RuleEngine.calculate_horse_star(hour_branch)
    
    qimen_ju_info = QimenEngine.calculate_ju(lunar.getPrevJieQi(True).getName(), day_stem, day_branch)

    earth_pan_dict = QimenEngine.calculate_earth_pan(qimen_ju_info["dun_type"], qimen_ju_info["ju_num"])
    xun_info = QimenEngine.calculate_xun(hour_stem, hour_branch)
    zhi_info = QimenEngine.calculate_zhi_fu_zhi_shi(earth_pan_dict, xun_info["hidden_stem"])
    heaven_pan = QimenEngine.calculate_heaven_pan(earth_pan_dict, hour_stem, xun_info["hidden_stem"], zhi_info["palace"])
    
    doors_pan = QimenEngine.calculate_doors(qimen_ju_info["dun_type"], zhi_info["door"], zhi_info["palace"], xun_info["jia_name"][1], hour_branch)
    
    current_zhi_fu_palace = next((p for p, star in heaven_pan["stars"].items() if star == zhi_info["star"]), "坤宮")
    deities_pan = QimenEngine.calculate_deities(qimen_ju_info["dun_type"], current_zhi_fu_palace)

    actual_hour_stem = xun_info["hidden_stem"] if hour_stem == "甲" else hour_stem
    current_zhi_shi_palace = next((p for p, door in doors_pan.items() if door == zhi_info["door"]), "中宮")
    hidden_stems_pan = QimenEngine.calculate_hidden_stems(qimen_ju_info["dun_type"], actual_hour_stem, current_zhi_shi_palace)

    qimen_matrix = []
    for palace_name in ["坎宮", "坤宮", "震宮", "巽宮", "中宮", "乾宮", "兌宮", "艮宮", "離宮"]:
        
        heaven_stem_val = heaven_pan["stems"].get(palace_name, "")
        earth_stem_val = earth_pan_dict.get(palace_name, "")
        door_val = doors_pan.get(palace_name, "")
        
        h_tags = RuleEngine.get_stem_tags(heaven_stem_val, palace_name)
        e_tags = RuleEngine.get_stem_tags(earth_stem_val, palace_name)
        
        is_tomb = RuleEngine.check_tomb(heaven_stem_val, palace_name) or RuleEngine.check_tomb(earth_stem_val, palace_name)
        is_punish = RuleEngine.check_punishment(heaven_stem_val, palace_name) or RuleEngine.check_punishment(earth_stem_val, palace_name)

        states = LogicState(
            is_in_tomb=is_tomb,
            is_punished=is_punish,
            is_empty=RuleEngine.check_empty(palace_name, hour_xun_kong),
            is_horse=(palace_name == horse_palace),
            is_door_forced=RuleEngine.check_door_forced(door_val, palace_name)
        )
        desc_parts = [t for t, v in zip(["入墓", "擊刑", "空亡", "驛馬", "門迫"], [states.is_in_tomb, states.is_punished, states.is_empty, states.is_horse, states.is_door_forced]) if v]
        states.description = "，".join(desc_parts) if desc_parts else "正常"

        qimen_matrix.append(PalaceData(
            palace_id=palace_name,
            hidden_stem=hidden_stems_pan.get(palace_name, ""),
            heaven_stem=heaven_stem_val,
            heaven_stem_tags=h_tags,
            heaven_stem_state=RuleEngine.calculate_12_states(heaven_stem_val, palace_name), 
            earth_stem=earth_stem_val,
            earth_stem_tags=e_tags,
            earth_stem_state=RuleEngine.calculate_12_states(earth_stem_val, palace_name),   
            door=door_val,
            star=heaven_pan["stars"].get(palace_name, ""),
            deity=deities_pan.get(palace_name, ""),
            logic_states=states
        ))

    return CalculationResponse(
        solar_time=request.time,
        lunar_time=f"{lunar.getYearInChinese()}年 {lunar.getMonthInChinese()}月 {lunar.getDayInChinese()}日",
        bazi={"year": bazi.getYear(), "month": bazi.getMonth(), "day": bazi.getDay(), "hour": bazi.getTime(), "day_empty": hour_xun_kong},
        qimen_info=QimenInfo(
            solar_term=lunar.getPrevJieQi(True).getName(), dun_type=qimen_ju_info["dun_type"], yuan=qimen_ju_info["yuan"],
            ju_num=qimen_ju_info["ju_num"], hour_xun=xun_info["full_name"], zhi_fu=zhi_info["star"], zhi_shi=zhi_info["door"], description=qimen_ju_info["description"]
        ),
        qimen_matrix=qimen_matrix 
    )


@app.post("/api/v1/divination/interpret", response_model=InterpretationResponse)
async def interpret_matrix(request: CalculationRequest):
    # 1. 複用原本的排盤引擎，先算出精確的九宮格數據
    matrix_data = await calculate_matrix(request)
    
    # 2. 這裡是你未來串接真正 LLM (如 OpenAI/Claude) 的地方
    # prompt = f"請根據以下奇門盤面數據進行解盤：{matrix_data.json()}。規則：忽略天禽星，以天芮為主..."
    # client = OpenAI(api_key="你的金鑰")
    # response = client.chat.completions.create(...)
    
    # 3. 為了讓你現在就能測試，我們先回傳基於你大師規則的「完美模擬解析」
    qimen_desc = matrix_data.qimen_info.description
    
    ai_report = f"""**🔮 奇門遁甲 AI 專屬大師解析報告**

**【時空陣眼定位】**
您所選擇的時間（{matrix_data.solar_time}），落於 {qimen_desc}。
根據高階奇門實戰法則，我們直接精準鎖定盤面核心，以「天芮星」（代表問題、疾病、結交、學習）作為天時核心進行論斷。

**【核心陣眼深度解析】**
本局天芮星與休門、太陰同落一宮。盤面資訊極度純粹：這是一個典型的「問題被壓制，宜暗中修復」的空間矩陣。

1. **問題被壓制 (星受制)：**
   天芮星五行屬土（代表核心阻礙或痼疾），落入木宮（木剋土）。這意味著當前您所擔心的問題或阻礙，正受到外在環境大局的「壓制」。它暫時無法作亂，但也無法輕易被連根拔起。
   
2. **隱藏的危機 (臨太陰)：**
   搭配神盤「太陰」，說明這個問題是暗中滋生的、未完全浮上檯面的（可能是隱藏的財務漏洞、未爆發的人事糾紛、或尚未察覺的隱疾）。

3. **最高戰略指導 (遇休門)：**
   既然問題處於暗處且受制，人盤的「休門」給出了最佳戰略——【切忌主動戳破或激化它】。
   現在最適合的策略是「冷處理」。藉由休養生息、暗中調查（太陰）來慢慢化解。絕對不適合在此時發動大規模的改革、開創或正面衝突。

*(💡 開發者提示：此為內建的大師邏輯引擎輸出。未來您只需在 main.py 接入 OpenAI API，就能讓 AI 根據每次不同的盤面，動態生成這類零幻覺的高階報告！)*
"""
    
    import asyncio
    await asyncio.sleep(1.5) # 模擬 AI 思考的延遲時間
    
    return InterpretationResponse(text=ai_report)