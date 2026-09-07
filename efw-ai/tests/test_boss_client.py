"""Boss 岗位解析纯函数测试（不联网、不启动浏览器）。"""
from app.worker.boss_client import parse_job_list

SAMPLE = '''
{"code":0,"zpData":{"jobList":[
  {"encryptJobId":"E1","jobName":"运维工程师","brandName":"某云科技",
   "salaryDesc":"15-25K","cityName":"武汉","encryptUserId":"U1",
   "jobUrl":"https://www.zhipin.com/job_detail/E1.html"}
]}}'''


def test_parse_job_list_fields():
    jobs = parse_job_list(SAMPLE)
    assert len(jobs) == 1
    assert jobs[0]["boss_job_id"] == "E1"
    assert jobs[0]["title"] == "运维工程师"
    assert jobs[0]["company"] == "某云科技"
    assert jobs[0]["salary_text"] == "15-25K"
    assert jobs[0]["city"] == "武汉"
    assert jobs[0]["boss_user_id"] == "U1"
    assert jobs[0]["job_url"] == "https://www.zhipin.com/job_detail/E1.html"


def test_parse_job_list_empty():
    assert parse_job_list('{"zpData":{"jobList":[]}}') == []


def test_parse_job_list_invalid_json_returns_empty():
    assert parse_job_list("not json") == []
    assert parse_job_list("") == []


def test_parse_job_list_missing_zpdata():
    assert parse_job_list('{"code":0}') == []


def test_parse_job_list_field_fallbacks():
    """Boss 不同接口字段名可能不同，需兜底。"""
    raw = '''{"zpData":{"jobList":[
      {"encryptJobId":"E2","jobName":"后端开发","companyName":"兜底公司",
       "salary":"20-30K","city":"北京","bossId":"U2","link":"/job/E2"}
    ]}}'''
    jobs = parse_job_list(raw)
    assert jobs[0]["boss_job_id"] == "E2"
    assert jobs[0]["title"] == "后端开发"
    assert jobs[0]["company"] == "兜底公司"
    assert jobs[0]["salary_text"] == "20-30K"
    assert jobs[0]["city"] == "北京"
    assert jobs[0]["boss_user_id"] == "U2"
    assert jobs[0]["job_url"] == "/job/E2"


def test_parse_job_list_skips_items_without_id():
    raw = '''{"zpData":{"jobList":[
      {"jobName":"无ID岗位"},
      {"encryptJobId":"E3","jobName":"有ID岗位"}
    ]}}'''
    jobs = parse_job_list(raw)
    assert len(jobs) == 1
    assert jobs[0]["boss_job_id"] == "E3"
