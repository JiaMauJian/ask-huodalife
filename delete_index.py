import json
with open('blog_index.json','r',encoding='utf-8') as f:
    index=json.load(f)
before=len(index)
index=[e for e in index if e['id']!='special_annual_returns']
with open('blog_index.json','w',encoding='utf-8') as f:
    json.dump(index,f,ensure_ascii=False)
print(f'刪除前 {before} 筆，刪除後 {len(index)} 筆')