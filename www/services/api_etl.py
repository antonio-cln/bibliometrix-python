from .utils import *
from . import metatagextraction


# ==============================================================================
# SCHEMA BLUEPRINT: THE 24 WOS-COMPLIANT TAGS
# ==============================================================================
WOS_COLUMNS = [
    "DB", "UT", "DI", "PMID", "TI", "SO", "JI", "PY", "DT", "LA", "TC", 
    "AU", "AF", "C1", "RP", "CR", "DE", "ID", "AB", "VL", "IS", "BP", "EP", "SR"
]

# ==============================================================================
# HELPER: UN-INVERT OPENALEX ABSTRACTS
# ==============================================================================
def parse_openalex_abstract(inverted_index):
    if not inverted_index:
        return None
    word_positions = []
    for word, positions in inverted_index.items():
        for pos in positions:
            word_positions.append((pos, word))
    word_positions.sort(key=lambda x: x[0])
    return " ".join([word for pos, word in word_positions])

# ==============================================================================
# TRANSLATOR: MAP OPENALEX JSON NODE -> WOS 24-TAG DICTIONARY
# ==============================================================================
def translate_openalex_record(item):
    biblio = item.get("biblio", {})
    
    # 1. Handle Authors lists exactly as required
    au_list = []
    af_list = []
    c1_list = []
    
    for authorship in item.get("authorships", []):
        full_name = authorship.get("author", {}).get("display_name", "")
        if full_name:
            # Full Name layout: "Surname, Firstname"
            parts = full_name.split()
            if len(parts) > 1:
                af_list.append(f"{parts[-1]}, {' '.join(parts[:-1])}")
                au_list.append(f"{parts[-1]} {''.join([p[0] for p in parts[:-1] if p.isalpha()])}")
            else:
                af_list.append(full_name)
                au_list.append(full_name)
                
        for inst in authorship.get("institutions", []):
            address_str = f"{inst.get('display_name')}, {inst.get('country_code', '')}".strip(", ")
            if address_str and address_str not in c1_list:
                c1_list.append(address_str)

    # 2. Extract keywords safely into clean list[str]
    author_keywords = [t.get("display_name") for t in item.get("topics", []) if t.get("display_name")]
    index_keywords = [c.get("display_name") for c in item.get("concepts", []) if c.get("display_name")]
    
    # 3. Extract cited reference IDs safely into list[str]
    references_list = [ref.split("/")[-1] for ref in item.get("referenced_works", [])]

    # 4. Handle Calculated Field: SR (Short Reference)
    first_author_surname = au_list[0].split()[0] if au_list else "Anon"
    pub_year = str(item.get("publication_year", ""))
    source_data = item.get("primary_location", {}).get("source", {}) if item.get("primary_location") else None
    journal_full = source_data.get("display_name", "") if source_data else ""
    if source_data:
        journal_short = source_data.get("abbreviated_title") # short_name?
        if not journal_short:
            journal_short = journal_full
    else:
        journal_short = ""
    #journal_short = item.get("primary_location", {}).get("source", {}).get("short_name", "Unknown")
    calculated_sr = f"{first_author_surname}, {pub_year}, {journal_short}"
  
    # Return the clean row dictionary with accurate Python types matching your table
    return {
        "DB": "OPENALEX",
        "UT": str(item.get("id", "")).split("/")[-1],
        "DI": str(item.get("doi", "")).replace("https://doi.org/", "") if item.get("doi") else "",
        "PMID": str(item.get("ids", {}).get("pmid", "")).split("/")[-1] if item.get("ids", {}).get("pmid") else "",
        "TI": str(item.get("title", "")),
        "SO": str(journal_full).upper() if journal_full else "", # Standardized uppercase
        "JI": str(journal_short),
        "PY": item.get("publication_year"), # Keep as int or convert to str depending on preference
        "DT": "Article" if item.get("type") == "journal-article" else str(item.get("type")).title(),
        "LA": str(item.get("language", "en")),
        "TC": int(item.get("cited_by_count", 0)), # Cast securely to int, defaults to 0
        
        # CLEAN LIST[STR] SHAPES
        "AU": au_list,       # list[str]
        "AF": af_list,       # list[str]
        "C1": c1_list,       # list[str]
        "CR": references_list, # list[str]
        "DE": author_keywords, # list[str]
        "ID": index_keywords,  # list[str]
        
        # STRING TRACKS
        "RP": c1_list[0] if c1_list else "",
        "AB": parse_openalex_abstract(item.get("abstract_inverted_index")), # String handler
        "VL": str(biblio.get("volume", "")) if biblio.get("volume") else "",
        "IS": str(biblio.get("issue", "")) if biblio.get("issue") else "",
        "BP": str(biblio.get("first_page", "")) if biblio.get("first_page") else "",
        "EP": str(biblio.get("last_page", "")) if biblio.get("last_page") else "",
        #"SR": calculated_sr   # Calculated Short Reference
    }

# ==============================================================================
# FETCHER: ENGINE KEYWORD SEARCH WITH PAGINATION LOOP
# ==============================================================================
def search_openalex_keywords(keyword, max_records=500):
    ## DEALING WITH PAGINATION
    master_records = []
    page = 1
    per_page = 200  # Max allowable items per single request on OpenAlex
    
    ## A VALID EMAIL ADDRESS SHOULD BE USED TO ROUTE THE SCRIPT TO THE "Polite Pool", ALLOWING FOR MORE REQUESTS PER SECOND WITHOUT BLOCKING THE IP
    headers = {"User-Agent": "GeneralPipeline/1.0 (mailto:your_email@example.com)"}
    
    print(f"Beginning API crawl for query keyword: '{keyword}'")
    
    while len(master_records) < max_records:
        url = "https://api.openalex.org/works"
        params = {
            "search": keyword,
            "page": page,
            "per_page": per_page
        }
        
        ## DEALING WITH RETRIES
        #response = requests.get(url, params=params, headers=headers)
        response = None
        max_retries = 5
        for attempt in range(max_retries):
            try:
                response = requests.get(url, params=params, headers=headers, timeout=15)
                
                # If it's a success, break out of the retry loop completely
                if response.status_code == 200:
                    break
                
                # If we get server errors (5xx) or rate limits (429), trigger backoff sleep
                if response.status_code in [429, 500, 502, 503, 504]:
                    sleep_time = 2 ** attempt  # 1s, 2s, 4s, 8s, 16s
                    print(f"[WARNING] Status {response.status_code} on page {page}. Retrying in {sleep_time}s... (Attempt {attempt + 1}/{max_retries})")
                    time.sleep(sleep_time)
                else:
                    # For unresolvable client issues (like a bad query format 400 or auth issue 403), do not back off
                    print(f"[FATAL ERROR] Client issue code {response.status_code} on page {page}.")
                    break
                    
            except (requests.exceptions.RequestException, requests.exceptions.Timeout) as e:
                sleep_time = 2 ** attempt
                print(f"[CONNECTION ERROR] {e} on page {page}. Retrying in {sleep_time}s... (Attempt {attempt + 1}/{max_retries})")
                time.sleep(sleep_time)

        if response.status_code != 200:
            print(f"Crawl broke on page {page}. Status: {response.status_code}")
            break
            
        payload = response.json()
        results = payload.get("results", [])
        
        if not results:
            print("Reached the end of available database records.")
            break
            
        for item in results:
            if len(master_records) >= max_records:
                break
            # Translate inline and save to processing cache
            standardized_dict = translate_openalex_record(item)
            master_records.append(standardized_dict)
            
        print(f"-> Retrieved and standardized {len(master_records)} total papers...")
        
        ## DEALING WITH RATE LIMITS
        # Paginate forward and avoid hitting server limits too quickly
        page += 1
        time.sleep(0.2)
    
    df = pd.DataFrame(master_records)
    df = metatagextraction.metaTagExtraction(df, Field='SR')
    return df

# ==============================================================================
# PIPELINE EXECUTION ENGINE
# ==============================================================================
if __name__ == "__main__":
    # 1. Define target search keywords
    #QUERY_KEYWORD = '"machine learning"' 
    QUERY_KEYWORD = input("What papers are you interested in? ")
    
    # 2. Run the bulk search extractor
    raw_standardized_data = search_openalex_keywords(QUERY_KEYWORD, max_records=250)
  
    # 3. Create DataFrame and enforce rigid Web of Science structure
    df = pd.DataFrame(raw_standardized_data, columns=WOS_COLUMNS)
    
    # 4. Diagnostics overview
    print("\nMaster Standardized DataFrame Built Successfully!")
    print(f"Shape: {df.shape[0]} rows x {df.shape[1]} columns")
    #print(df[["DB", "UT", "DI", "TI", "PY", "TC"]].head())
    
    # Save directly out as a mock Web of Science field export CSV
    #df.to_csv("wos_standardized_output.csv", index=False)
    
    print(df)
    df = metatagextraction.metaTagExtraction(df, Field='SR')
    print(df)