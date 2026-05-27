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
# HELPER: EXTRACT AND UNIFY PUBMED ABSTRACT SECTIONS
# ==============================================================================
def parse_pubmed_abstract(abstract_node):
    """
    PubMed abstracts can be split across multiple 'AbstractText' XML nodes 
    if the paper uses a structured format (e.g., Background, Methods, Results).
    This collects and stitches them into a unified, flat plaintext string.
    """
    if abstract_node is None:
        return ""
    
    parts = []
    for text_node in abstract_node.findall("AbstractText"):
        # Check if there is a section label (e.g., BACKGROUND:)
        label = text_node.get("Label")
        text = "".join(text_node.itertext()).strip()
        if text:
            if label:
                parts.append(f"{label}: {text}")
            else:
                parts.append(text)
                
    return " ".join(parts) if parts else ""

# ==============================================================================
# HELPER: WEB OF SCIENCE ABSTRACT PARSER
# ==============================================================================
def parse_wos_abstract(abstract_node):
    """
    Web of Science stores abstracts as structured multi-paragraph structures 
    under an abstract text node loop. This flattens them cleanly to a string.
    """
    if not abstract_node or "abstractText" not in abstract_node:
        return ""
    
    p_nodes = abstract_node.get("abstractText", {}).get("p", [])
    if isinstance(p_nodes, list):
        return " ".join([str(p).strip() for p in p_nodes if p])
    return str(p_nodes).strip()

# ==============================================================================
# HELPER: EXTRACT SCOPUS PLAIN TEXT ABSTRACTS
# ==============================================================================
def parse_scopus_abstract(entry_node):
    """
    The standard Scopus Search API returns a short, clean summary snippet 
    directly inside the search loop under the 'dc:description' tag.
    """
    return entry_node.get("dc:description", "").strip()

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
        "SR": calculated_sr   # Calculated Short Reference
    }

# ==============================================================================
# TRANSLATOR: MAP PUBMED XML ARTICLE -> WOS 24-TAG DICTIONARY
# ==============================================================================
def translate_pubmed_record(pubmed_article):
    """
    Parses an individual <PubmedArticle> XML element node and extracts
    the exact data types matching your structural dataframe requirements.
    """
    medline = pubmed_article.find("MedlineCitation")
    article = medline.find("Article") if medline is not None else None
    journal = article.find("Journal") if article is not None else None
    
    if medline is None or article is None:
        return None

    # Extract clean primary PMIDs
    pmid_str = medline.findtext("PMID", "").strip()

    # Extract title
    title_node = article.find("ArticleTitle")

    # Extract DOIs from the ArticleIdList wrapper block
    doi_str = ""
    pub_med_data = pubmed_article.find("PubmedData")
    if pub_med_data is not None:
        article_ids = pub_med_data.find("ArticleIdList")
        if article_ids is not None:
            for aid in article_ids.findall("ArticleId"):
                if aid.get("IdType") == "doi":
                    doi_str = "".join(aid.itertext()).strip()

    # Extract Authors arrays (AU, AF, C1)
    au_list = []
    af_list = []
    c1_list = []
    
    author_list_node = article.find("AuthorList")
    if author_list_node is not None:
        for author in author_list_node.findall("Author"):
            last_name = author.findtext("LastName", "").strip()
            fore_name = author.findtext("ForeName", "").strip()
            initials = author.findtext("Initials", "").strip()
            
            if last_name:
                # AF layout: "LastName, ForeName"
                af_list.append(f"{last_name}, {fore_name}" if fore_name else last_name)
                # AU layout: "LastName Initials"
                au_list.append(f"{last_name} {initials}" if initials else last_name)
                
            # Process institutional affiliation string tracking nodes
            affiliation_info = author.find("AffiliationInfo")
            if affiliation_info is not None:
                aff_text = affiliation_info.findtext("Affiliation", "").strip()
                if aff_text and aff_text not in c1_list:
                    c1_list.append(aff_text)
                    
    cr_list = []
    comments_corrections = medline.find("CommentsCorrectionsList")
    if comments_corrections is not None:
        for ref in comments_corrections.findall("CommentsCorrections"):
            # Target explicit citation records
            if ref.get("RefType") == "Cites":
                pmid_node = ref.find("PMID")
                
                # Only add if a valid target PMID exists
                if pmid_node is not None and pmid_node.text:
                    clean_pmid = pmid_node.text.strip()
                    cr_list.append(f"PMID:{clean_pmid}")

    # Extract MeSH and Keywords (DE, ID)
    author_keywords = []
    keyword_list_node = medline.find("KeywordList")
    if keyword_list_node is not None:
        author_keywords = ["".join(k.itertext()).strip() for k in keyword_list_node.findall("Keyword") if k.text]

    mesh_keywords = []
    mesh_heading_list = medline.find("MeshHeadingList")
    if mesh_heading_list is not None:
        for heading in mesh_heading_list.findall("MeshHeading"):
            desc = heading.find("DescriptorName")
            if desc is not None:
                mesh_keywords.append("".join(desc.itertext()).strip())

    # Journal details processing (SO, JI, VL, IS, BP, EP)
    journal_full = journal.findtext("Title", "") if journal is not None else ""
    journal_short = journal.findtext("ISOAbbreviation", "") if journal is not None else ""
    if not journal_short:
        journal_short = journal_full

    journal_issue = journal.find("JournalIssue") if journal is not None else None
    volume = journal_issue.findtext("Volume", "") if journal_issue is not None else ""
    issue = journal_issue.findtext("Issue", "") if journal_issue is not None else ""
    
    # Safely extract 4-digit Publication Year
    pub_year = ""
    if journal_issue is not None:
        pub_date = journal_issue.find("PubDate")
        if pub_date is not None:
            pub_year = pub_date.findtext("Year", "").strip()
            if not pub_year:
                # Fallback pattern for unstructured string dates like '2024 Mar-Apr'
                medline_date = pub_date.findtext("MedlineDate", "").strip()
                if medline_date:
                    pub_year = medline_date[:4]

    # Handle layout pages boundaries
    bp_str, ep_str = "", ""
    pagination = article.find("Pagination")
    if pagination is not None:
        medline_pg = pagination.findtext("MedlinePgn", "").strip()
        if medline_pg:
            if "-" in medline_pg:
                parts = medline_pg.split("-")
                bp_str = parts[0]
                ep_str = parts[1]
            else:
                bp_str = medline_pg

    # Handle Calculated Short Reference (SR) field
    first_author_surname = au_list[0].split()[0] if au_list else "Anon"
    calculated_sr = f"{first_author_surname}, {pub_year}, {journal_short}"

    return {
        "DB": "PUBMED",
        "UT": pmid_str,
        "DI": doi_str,
        "PMID": pmid_str,
        "TI": "".join(title_node.itertext()).strip() if title_node is not None else "",
        "SO": str(journal_full).upper() if journal_full else "",
        "JI": str(journal_short),
        "PY": int(pub_year) if pub_year.isdigit() else None,
        "DT": "Article",  # Default baseline class mapping for standard index
        "LA": article.findtext("Language", "eng"),
        "TC": 0,  # PubMed doesn't expose native citation counts directly via efetch XML
        
        # REQUIRED CLEAN LIST[STR] STRUCTURES
        "AU": au_list,       
        "AF": af_list,       
        "C1": c1_list,       
        "CR": cr_list,
        "DE": author_keywords, 
        "ID": mesh_keywords,  
        
        # REMAINING FIELDS
        "RP": c1_list[0] if c1_list else "",
        "AB": parse_pubmed_abstract(article.find("Abstract")),
        "VL": volume,
        "IS": issue,
        "BP": bp_str,
        "EP": ep_str,
        "SR": calculated_sr
    }

# ==============================================================================
# TRANSLATOR: MAP WOS JSON RECORD -> NATIVE 24-TAG DICTIONARY
# ==============================================================================
def translate_wos_record(item):
    """
    Translates an Expanded Web of Science API JSON document node 
    into a clean dictionary matching the strict types of your table schema.
    """
    # Drill down to core record metadata wrappers
    uid = item.get("UID", "")
    static_data = item.get("staticData", {})
    summary = static_data.get("summary", {})
    full_record = static_data.get("fullRecordData", {})
    dynamic_data = item.get("dynamicData", {})
    
    # Titles Extraction (TI)
    title_list = summary.get("titles", {}).get("title", [])
    ti_str = ""
    so_str = ""
    for t in title_list:
        if t.get("type") == "item":
            ti_str = t.get("content", "")
        elif t.get("type") == "source":
            so_str = t.get("content", "")

    # ISO Abbreviation Tracking (JI)
    ji_str = ""
    for t in summary.get("titles", {}).get("title", []):
        if t.get("type") == "source_abbrev":
            ji_str = t.get("content", "")
    if not ji_str:
        ji_str = so_str

    # Process Core Authors Arrays (AU, AF)
    au_list = []
    af_list = []
    names_node = summary.get("names", {}).get("name", [])
    if isinstance(names_node, dict):  # Safe fallback if single item dict instead of list
        names_node = [names_node]
        
    for name in names_node:
        if name.get("role") == "author":
            # AU -> "Surname Initials"
            wos_standard_name = name.get("wosStandard", "")
            if wos_standard_name:
                au_list.append(wos_standard_name)
            
            # AF -> "Surname, Given Name"
            full_name = name.get("full_name", "")
            if full_name:
                af_list.append(full_name)

    # Process Institutional Affiliations Matrix (C1, RP)
    c1_list = []
    rp_str = ""
    reprint_nodes = full_record.get("reprint", {}).get("address", [])
    if isinstance(reprint_nodes, dict):
        reprint_nodes = [reprint_nodes]
    if reprint_nodes and "full_address" in reprint_nodes[0]:
        rp_str = reprint_nodes[0].get("full_address", "")

    addresses_node = full_record.get("addresses", {}).get("address", [])
    if isinstance(addresses_node, dict):
        addresses_node = [addresses_node]
    for addr in addresses_node:
        full_addr = addr.get("full_address", "")
        if full_addr and full_addr not in c1_list:
            c1_list.append(full_addr)

    # External Crossref Identifiers (DI, PMID)
    doi_str = ""
    pmid_str = ""
    for id_node in item.get("identifiers", {}).get("identifier", []):
        if id_node.get("type") == "doi":
            doi_str = id_node.get("value", "")
        elif id_node.get("type") == "pmid":
            pmid_str = id_node.get("value", "")

    # Document Classification & Metadata
    pub_year = summary.get("pub_info", {}).get("pubyear")
    doc_type = summary.get("doctypes", {}).get("doctype", ["Article"])[0]
    lang_str = summary.get("count", {}).get("language", ["English"])[0]
    
    # Citation Counts (TC)
    tc_val = 0
    tc_nodes = dynamic_data.get("citation_matrix", {}).get("wos", [])
    if tc_nodes:
        tc_val = int(dynamic_data.get("citation_matrix", {}).get("wos", [{}])[0].get("count", 0))

    # Keywords Arrays Processing (DE, ID)
    author_keywords = []
    keywords_plus = []
    kw_node = full_record.get("keywords", {}).get("keyword", [])
    if isinstance(kw_node, str):
        author_keywords = [kw_node]
    elif isinstance(kw_node, list):
        author_keywords = [str(k) for k in kw_node]

    # Bibliographies (CR)
    references_list = []
    refs_node = full_record.get("references", {}).get("reference", [])
    if isinstance(refs_node, dict):
        refs_node = [refs_node]
    for ref in refs_node:
        ref_uid = ref.get("uid", "")
        if ref_uid:
            references_list.append(ref_uid)

    # Handle Calculated Short Reference (SR) field
    first_author_surname = au_list[0].split()[0] if au_list else "Anon"
    calculated_sr = f"{first_author_surname}, {pub_year}, {ji_str}"

    return {
        "DB": "WEB_OF_SCIENCE",
        "UT": uid,
        "DI": doi_str,
        "PMID": pmid_str,
        "TI": ti_str,
        "SO": str(so_str).upper().strip().strip('"' + '“' + '”') if so_str else "",
        "JI": str(ji_str),
        "PY": int(pub_year) if str(pub_year).isdigit() else pub_year,
        "DT": str(doc_type).title(),
        "LA": str(lang_str),
        "TC": tc_val,
        
        # REQUIRED CLEAN LIST[STR] STRUCTURES
        "AU": au_list,       
        "AF": af_list,       
        "C1": c1_list,       
        "CR": references_list, 
        "DE": author_keywords, 
        "ID": keywords_plus, # Populated if tracking tags present in Expanded response block
        
        # STRING TRACKS
        "RP": rp_str if rp_str else (c1_list[0] if c1_list else ""),
        "AB": parse_wos_abstract(full_record.get("abstracts", {}).get("abstract", {})),
        "VL": str(summary.get("pub_info", {}).get("vol", "")),
        "IS": str(summary.get("pub_info", {}).get("issue", "")),
        "BP": str(summary.get("pub_info", {}).get("page", {}).get("begin", "")),
        "EP": str(summary.get("pub_info", {}).get("page", {}).get("end", "")),
        "SR": calculated_sr   
    }

# ==============================================================================
# TRANSLATOR: MAP SCOPUS JSON ENTRY -> WOS 24-TAG DICTIONARY
# ==============================================================================
def translate_scopus_record(item):
    """
    Parses a single Scopus Search JSON entry object and maps the keys
    into the strict types and layouts required by your Master DataFrame.
    """
    # Unique Identifier parsing (UT)
    scopus_id = item.get("dc:identifier", "").replace("SCOPUS_ID:", "")

    # Publication names handling (SO, JI)
    journal_full = item.get("prism:publicationName", "")
    # Scopus doesn't always provide an ISO abbrev in search hits; fall back to full name
    journal_short = journal_full 

    # Clean Author string splitting (AU, AF)
    au_list = []
    af_list = []
    
    # Scopus Search returns a clean, pre-joined string of authors separated by ';'
    author_string = item.get("author_names", "")
    if author_string:
        raw_names = [name.strip() for name in author_string.split(";") if name.strip()]
        for name in raw_names:
            af_list.append(name) # "Surname, Given Name" format matches AF
            
            # Convert to AU style: "Surname Initials"
            if "," in name:
                parts = name.split(",")
                surname = parts[0].strip()
                given = parts[1].strip()
                initials = "".join([g[0] for g in given.split() if g.isalpha()])
                au_list.append(f"{surname} {initials}".strip())
            else:
                au_list.append(name)

    # Scopus does not return full institutional lists or references inside the 
    # baseline search hits. We initialize empty lists/placeholders for structural integrity.
    c1_list = []
    
    # Safely extract core publication year (PY)
    cover_date = item.get("prism:coverDate", "")
    pub_year = None
    if cover_date and len(cover_date) >= 4:
        pub_year = int(cover_date[:4])

    # Handle Page Number bounds split tracking
    page_range = item.get("prism:pageRange", "")
    bp_str, ep_str = "", ""
    if page_range and "-" in page_range:
        parts = page_range.split("-")
        bp_str, ep_str = parts[0].strip(), parts[1].strip()
    elif page_range:
        bp_str = page_range.strip()

    # Handle Calculated Short Reference (SR) field
    first_author_surname = au_list[0].split()[0] if au_list else "Anon"
    calculated_sr = f"{first_author_surname}, {pub_year}, {journal_short}"

    return {
        "DB": "SCOPUS",
        "UT": scopus_id,
        "DI": item.get("prism:doi", ""),
        "PMID": item.get("pubmed-id", ""),
        "TI": item.get("dc:title", "").strip(),
        "SO": str(journal_full).upper().strip().strip('"' + '“' + '”') if journal_full else "",
        "JI": str(journal_short),
        "PY": pub_year,
        "DT": str(item.get("subtypeDescription", "Article")).title(),
        "LA": "English",  # Scopus baseline defaults indexing tracker
        "TC": int(item.get("citedby-count", 0)),
        
        # REQUIRED CLEAN LIST[STR] STRUCTURES
        "AU": au_list,       
        "AF": af_list,       
        "C1": c1_list,       
        "CR": [],  
        "DE": [], # Detailed indexing vectors are stored in secondary abstract retrievals
        "ID": [],  
        
        # STRING TRACKS
        "RP": "",
        "AB": parse_scopus_abstract(item),
        "VL": str(item.get("prism:volume", "")),
        "IS": str(item.get("prism:issueIdentifier", "")),
        "BP": bp_str,
        "EP": ep_str,
        "SR": calculated_sr   
    }

# ==============================================================================
# FETCHER: ENGINE KEYWORD SEARCH WITH PAGINATION LOOP
# ==============================================================================
def search_openalex_keywords(keyword, max_records=500, key=""):
    ## DEALING WITH PAGINATION
    master_records = []
    page = 1
    per_page = 200  # Max allowable items per single request on OpenAlex
    
    ## A VALID EMAIL ADDRESS SHOULD BE USED TO ROUTE THE SCRIPT TO THE "Polite Pool", ALLOWING FOR MORE REQUESTS PER SECOND WITHOUT BLOCKING THE IP
    headers = {"User-Agent": "GeneralPipeline/1.0 (mailto:your_email@example.com)"}
    
    print(f"Beginning OpenAlex API crawl for query keyword: '{keyword}'")
    
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
    #df = metatagextraction.metaTagExtraction(df, Field='SR')
    return df

# ==============================================================================
# FETCHER: PUBMED SELECTION / EXTRACTION SYSTEM WITH EXPONENTIAL BACKOFF
# ==============================================================================
def search_pubmed_keywords(keyword, max_records=500, key=""):
    master_records = []
    
    # PubMed API limits un-registered developers to 3 calls/sec
    headers = {"User-Agent": "GeneralPipeline/1.0 (mailto:your_email@example.com)"}
    
    # --------------------------------------------------------------------------
    # PHASE A: EXECUTE KEYWORD LOOKUP (GET IDS MATRIX)
    # --------------------------------------------------------------------------
    search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    search_params = {
        "db": "pubmed",
        "term": keyword,
        "retmode": "json",
        "retmax": max_records
    }
    
    print(f"Beginning PubMed API crawl for query keyword: '{keyword}'")
    
    search_response = None
    for attempt in range(5):
        try:
            search_response = requests.get(search_url, params=search_params, headers=headers, timeout=15)
            if search_response.status_code == 200:
                break
            if search_response.status_code in [429, 500, 502, 503, 504]:
                time.sleep(2 ** attempt)
        except requests.exceptions.RequestException:
            time.sleep(2 ** attempt)
            
    if search_response is None or search_response.status_code != 200:
        print("[CRITICAL] PubMed search step failed to execute.")
        return []
        
    id_list = search_response.json().get("esearchresult", {}).get("idlist", [])
    if not id_list:
        print("No matching records found in NCBI registry.")
        return []
        
    print(f"-> Target ID set resolved. Found {len(id_list)} documents. Commencing bulk XML download...")

    # --------------------------------------------------------------------------
    # PHASE B: BATCH FETCH METADATA FOR RESOLVED RECORDS
    # --------------------------------------------------------------------------
    fetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    
    # Chunk long list of PMIDs into safe packages of 200 items per call
    chunk_size = 200
    for i in range(0, len(id_list), chunk_size):
        chunk_ids = id_list[i : i + chunk_size]
        
        fetch_params = {
            "db": "pubmed",
            "id": ",".join(chunk_ids),
            "retmode": "xml"  # Forces XML payload format extraction
        }
        
        fetch_response = None
        for attempt in range(5):
            try:
                fetch_response = requests.get(fetch_url, params=fetch_params, headers=headers, timeout=30)
                if fetch_response.status_code == 200:
                    break
                if fetch_response.status_code in [429, 500, 502, 503, 504]:
                    time.sleep(2 ** attempt)
            except requests.exceptions.RequestException:
                time.sleep(2 ** attempt)
                
        if fetch_response is None or fetch_response.status_code != 200:
            print(f"[WARNING] Skipping batch group range indices {i}-{i+chunk_size} due to API extraction faults.")
            continue
            
        # Parse returned XML payload package block elements natively
        try:
            root = ET.fromstring(fetch_response.content)
            for xml_article in root.findall("PubmedArticle"):
                record = translate_pubmed_record(xml_article)
                if record:
                    master_records.append(record)
        except ET.ParseError as xml_error:
            print(f"[ERROR] XML document formatting parse breakdown: {xml_error}")
            
        print(f"-> Parsed and translated {len(master_records)} total records from PubMed...")
        time.sleep(0.3)  # Respect NCBI baseline throttling boundaries
        
    df = pd.DataFrame(master_records)
    #df = metatagextraction.metaTagExtraction(df, Field='SR')
    return df

# ==============================================================================
# FETCHER: WOS SEARCH QUERY SYSTEM WITH EXPONENTIAL BACKOFF
# ==============================================================================
def search_wos_keywords(keyword, max_records=500, key=""):
    master_records = []
    first_record = 1
    count = 50  # Records per batch request limit for WoS API
    
    # PASTE YOUR WEB OF SCIENCE EXPANDED API KEY HERE
    WOS_API_KEY = key
    
    headers = {
        "X-ApiKey": WOS_API_KEY,
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    print(f"Beginning Web of Science API crawl for query keyword: '{keyword}'")
    
    while len(master_records) < max_records:
        url = "https://api.clarivate.com/apis/wos-starter/v1/documents"
        params = {
            "q": f"TS={keyword}",  # TS targets Topic Field (Title, Abstract, Keywords)
            "limit": count,
            "page": first_record
        }
        
        # --- EXPONENTIAL BACKOFF RETRY LAYER ---
        response = None
        max_retries = 5
        for attempt in range(max_retries):
            try:
                response = requests.get(url, params=params, headers=headers, timeout=20)
                
                if response.status_code == 200:
                    break
                
                if response.status_code in [429, 500, 502, 503, 504]:
                    sleep_time = 2 ** attempt
                    print(f"[WARNING] WoS API Status {response.status_code}. Retrying in {sleep_time}s... (Attempt {attempt + 1}/{max_retries})")
                    time.sleep(sleep_time)
                else:
                    print(f"[FATAL ERROR] WoS Client issue code {response.status_code}.")
                    break
                    
            except (requests.exceptions.RequestException, requests.exceptions.Timeout) as e:
                sleep_time = 2 ** attempt
                print(f"[CONNECTION ERROR] {e}. Retrying in {sleep_time}s... (Attempt {attempt + 1}/{max_retries})")
                time.sleep(sleep_time)
        
        if response is None or response.status_code != 200:
            print(f"\n[CRITICAL FAILURE] Pipeline halted at record offset {first_record}.")
            break
        # ---------------------------------------
            
        payload = response.json()
        results = payload.get("Data", {}).get("Records", {}).get("record", [])
        
        # Stop if no more records exist
        if not results:
            print("Reached the end of available Web of Science database records.")
            break
            
        # Ensure results are consistently list format
        if isinstance(results, dict):
            results = [results]
            
        for item in results:
            if len(master_records) >= max_records:
                break
            standardized_dict = translate_wos_record(item)
            if standardized_dict:
                master_records.append(standardized_dict)
            
        print(f"-> Retrieved and standardized {len(master_records)} total papers from WoS...")
        
        # Paginate forward by tracking starting index positions
        first_record += count
        time.sleep(0.5)  # Standard safety spacing for throttle limits

    df = pd.DataFrame(master_records)
    #df = metatagextraction.metaTagExtraction(df, Field='SR')
    return df

# ==============================================================================
# FETCHER: SCOPUS SEARCH ENGINE WITH EXPONENTIAL BACKOFF RETRY LOOP
# ==============================================================================
def search_scopus_keywords(keyword, max_records=500, key=" "):
    master_records = []
    start_index = 0
    count = 25  # Scopus standard default count limit per search loop request
    
    # --------------------------------------------------------------------------
    # CRITICAL: PROVIDE YOUR SCOPUS API KEY & INSTTOKEN HERE
    # --------------------------------------------------------------------------
    SCOPUS_API_KEY = key
    SCOPUS_INST_TOKEN = ""  # Leave blank if you are running on your University VPN
    
    headers = {
        "X-ELS-APIKey": SCOPUS_API_KEY,
        "Accept": "application/json"
    }
    if SCOPUS_INST_TOKEN:
        headers["X-ELS-Insttoken"] = SCOPUS_INST_TOKEN
        
    print(f"Beginning Scopus API crawl for query keyword: '{keyword}'")
    
    while len(master_records) < max_records:
        url = "https://api.elsevier.com/content/search/scopus"
        params = {
            "query": f"TITLE-ABS-KEY({keyword})",  # Search Title, Abstract, and Keywords
            "count": count,
            "start": start_index
        }
        
        # --- EXPONENTIAL BACKOFF RETRY LAYER ---
        response = None
        max_retries = 5
        for attempt in range(max_retries):
            try:
                response = requests.get(url, params=params, headers=headers, timeout=20)
                
                if response.status_code == 200:
                    break
                
                if response.status_code in [429, 500, 502, 503, 504]:
                    sleep_time = 2 ** attempt
                    print(f"[WARNING] Scopus Status {response.status_code}. Retrying in {sleep_time}s... (Attempt {attempt + 1}/{max_retries})")
                    time.sleep(sleep_time)
                else:
                    print(f"[FATAL ERROR] Scopus Client issue code {response.status_code}. Checking authentication/query syntax layout.")
                    break
                    
            except (requests.exceptions.RequestException, requests.exceptions.Timeout) as e:
                sleep_time = 2 ** attempt
                print(f"[CONNECTION ERROR] {e}. Retrying in {sleep_time}s... (Attempt {attempt + 1}/{max_retries})")
                time.sleep(sleep_time)
        
        if response is None or response.status_code != 200:
            print(f"\n[CRITICAL FAILURE] Pipeline halted. Failed to parse Scopus records at offset index {start_index}.")
            break
        # ---------------------------------------
            
        payload = response.json()
        search_results = payload.get("search-results", {})
        entries = search_results.get("entry", [])
        
        # Break out if there's no more data left on the server
        if not entries or (isinstance(entries, list) and len(entries) == 1 and "error" in entries[0]):
            print("Reached the end of available Scopus database records.")
            break
            
        for item in entries:
            if len(master_records) >= max_records:
                break
            standardized_dict = translate_scopus_record(item)
            if standardized_dict:
                master_records.append(standardized_dict)
                
        print(f"-> Retrieved and standardized {len(master_records)} total papers from Scopus...")
        
        # Paginate forward by incrementing the cursor starting offset point
        start_index += count
        time.sleep(0.3)  # Maintain steady pacing for standard Scopus rate boundaries
        
    df = pd.DataFrame(master_records)
    #df = metatagextraction.metaTagExtraction(df, Field='SR')
    return df

# ==============================================================================
# PIPELINE EXECUTION ENGINE
# ==============================================================================
if __name__ == "__main__":
    # Define target search keywords
    QUERY_KEYWORD = input("What papers are you interested in? ")
    
    ## PubMed
    # Run the bulk search extractor
    raw_standardized_data = search_pubmed_keywords(QUERY_KEYWORD, max_records=250)

    # Create DataFrame and enforce rigid Web of Science structure
    df = pd.DataFrame(raw_standardized_data, columns=WOS_COLUMNS)
    
    # Diagnostics overview
    print("\nStandardized DataFrame has been built")
    print(f"Shape: {df.shape[0]} rows x {df.shape[1]} columns")
    
    # Save directly out as a mock Web of Science field export CSV
    df.to_csv("standardized_output_pubmed.csv", index=False)
    
    print(df)

    ## OpenAlex
    # Run the bulk search extractor
    #raw_standardized_data = search_openalex_keywords(QUERY_KEYWORD, max_records=250)

    # Create DataFrame and enforce rigid Web of Science structure
    #df = pd.DataFrame(raw_standardized_data, columns=WOS_COLUMNS)
    
    # Diagnostics overview
    #print("\nStandardized DataFrame has been built")
    #print(f"Shape: {df.shape[0]} rows x {df.shape[1]} columns")
    
    # Save directly out as a mock Web of Science field export CSV
    #df.to_csv("standardized_output_openalex.csv", index=False)
    
    #print(df)

    ## Web of Science
    # Run the bulk search extractor
    #raw_standardized_data = search_wos_keywords(QUERY_KEYWORD, max_records=250, key="e4058bb1d97e5b5e81f91420f5969682a7c4d585")

    # Create DataFrame and enforce rigid Web of Science structure
    #df = pd.DataFrame(raw_standardized_data, columns=WOS_COLUMNS)
    
    # Diagnostics overview
    #print("\nStandardized DataFrame has been built")
    #print(f"Shape: {df.shape[0]} rows x {df.shape[1]} columns")
    
    # Save directly out as a mock Web of Science field export CSV
    #df.to_csv("standardized_output_wos.csv", index=False)
    
    #print(df)

    ## Scopus
    # Run the bulk search extractor
    raw_standardized_data = search_scopus_keywords(QUERY_KEYWORD, max_records=250, key="7e82d42f0516806e97a3ff59f3474bd9")

    # Create DataFrame and enforce rigid Web of Science structure
    df = pd.DataFrame(raw_standardized_data, columns=WOS_COLUMNS)
    
    # Diagnostics overview
    print("\nStandardized DataFrame has been built")
    print(f"Shape: {df.shape[0]} rows x {df.shape[1]} columns")
    
    # Save directly out as a mock Web of Science field export CSV
    df.to_csv("standardized_output_scopus.csv", index=False)
    
    print(df)