"""H-1B / H-2B employer dashboard.

Run from the repo root:  streamlit run dashboard/app.py
Reads h1b-data/research.db (or the file named by the RESEARCH_DB env var), read-only.
"""
import pandas as pd
import streamlit as st

import queries as q

st.set_page_config(page_title="Employer lookup", layout="wide")


@st.cache_resource
def db():
    try:
        return q.connect()
    except FileNotFoundError:
        with st.spinner("Downloading the database (about 55 MB, first start only)..."):
            q.download_db()
        return q.connect()


def money(x):
    return f"${x:,.0f}"


def count(x):
    return "-" if x is None else f"{x:,}"


def table(rows, columns, rename=None):
    df = pd.DataFrame(rows, columns=columns)
    return df.rename(columns=rename or {})


def search_view(con):
    st.title("Employer lookup")
    text = st.text_input("Company name", placeholder="e.g. Acme Farms")
    if not text:
        st.caption("Search H-1B and H-2B employers by name or trade name (DBA).")
        return
    hits = q.search_employers(con, text)
    if not hits:
        st.info("No employers match that name.")
        return
    st.caption(f"{len(hits)} employers" + (" (first 50)" if len(hits) == 50 else ""))
    for h in hits:
        cols = st.columns([5, 1, 2, 1, 1])
        label = h["employer_name"] + (f" (DBA {h['dba']})" if h["dba"] else "")
        cols[0].markdown(f"**{label}**  \n{h['city']}, {h['state']}")
        cols[1].write(h["program"])
        cols[2].write(f"{h['n_applications']:,} applications")
        cols[3].write(f"{h['n_cases']} cases")
        if cols[4].button("Open", key=f"open-{h['employer_id']}"):
            st.query_params["employer"] = str(h["employer_id"])
            st.rerun()


def employer_view(con, employer_id):
    e = q.employer(con, employer_id)
    if not e:
        st.error("No employer with that id.")
        return
    if st.button("← Back to search"):
        st.query_params.clear()
        st.rerun()

    st.title(e["employer_name"])
    flags = [e["program"]]
    if e["willful_violator"]:
        flags.append("Willful violator (DOL flag)")
    if e["h1b_dependent"]:
        flags.append("H-1B dependent")
    st.markdown(f"{e['address']}, {e['city']}, {e['state']} {e['zip5']}  ·  "
                f"Tax ID {e['fein'] or 'not given'}  ·  NAICS {e['naics'] or '-'}  ·  " + "  ·  ".join(flags))
    if e["dba"]:
        st.caption(f"Also does business as {e['dba']}")

    s = q.summary(con, employer_id)
    c = st.columns(5)
    c[0].metric("Applications", f"{s['applications']:,}")
    c[1].metric("Certified", f"{s['certified']:,}")
    c[2].metric("Linked WHD cases", s["cases"])
    c[3].metric("Back wages found", money(s["back_wages"]))
    c[4].metric("Penalties assessed", money(s["penalties"]))

    related = q.same_tax_id(con, employer_id)
    if related:
        with st.expander(f"Same tax ID elsewhere ({len(related)})"):
            for r in related:
                if st.button(f"{r['employer_name']} · {r['city']}, {r['state']} · {r['program']} · "
                             f"{r['n_applications']:,} applications", key=f"rel-{r['employer_id']}"):
                    st.query_params["employer"] = str(r["employer_id"])
                    st.rerun()

    st.subheader("Wage and Hour cases")
    cs = q.cases(con, employer_id)
    if not cs:
        st.write("No WHD enforcement case is linked to this employer.")
    else:
        st.caption("WHD records have no tax ID, so each case is linked by name and location. "
                   "Check the WHD name and address against this employer before relying on a link.")
        for v in cs:
            title = (f"Case {v['case_id']} · {(v['findings_end_date'] or '')[:10]} · "
                     f"{v['trade_nm'] or v['legal_name']} · back wages {money(v['bw_atp_amt'] or 0)}")
            with st.expander(title):
                st.markdown(f"**WHD record:** {v['legal_name'] or '-'} (trade name {v['trade_nm'] or '-'}), "
                            f"{v['street_addr_1_txt']}, {v['cty_nm']}, {v['st_cd']} {v['zip_cd']}")
                st.markdown(f"**Period checked:** {(v['findings_start_date'] or '')[:10]} to "
                            f"{(v['findings_end_date'] or '')[:10]}")
                # Text cells throughout: blanks mixed with numbers break Streamlit's table conversion.
                st.table(pd.DataFrame([
                    ["All laws", count(v["case_violtn_cnt"]), money(v["bw_atp_amt"] or 0),
                     count(v["ee_violtd_cnt"])],
                    ["H-1B", count(v["h1b_violtn_cnt"]), money(v["h1b_bw_atp_amt"] or 0), ""],
                    ["H-2B", count(v["h2b_violtn_cnt"]), money(v["h2b_bw_atp_amt"] or 0), ""],
                    ["H-2A", count(v["h2a_violtn_cnt"]), "", ""],
                    ["Minimum wage / overtime (FLSA)", count(v["flsa_violtn_cnt"]), "", ""],
                ], columns=["Law", "Violations", "Back wages", "Workers"]).set_index("Law"))
                st.markdown(f"**Penalties assessed:** {money(v['cmp_assd'] or 0)}")
                st.info(q.match_label(v["method"], v["est_false_match_rate"]) +
                        f" (WHD {v['whd_name_field']} vs employer {v['employer_name_field']}).")
                st.caption(f"Source: WHD enforcement API {v['source_urls']}, case_id {v['case_id']}, "
                           f"loaded by DOL {v['load_dt']}; file {v['source_file']} "
                           f"(sha256 {v['source_sha256'][:12]}…)")

    st.subheader("Visa applications")
    apps = q.applications(con, employer_id)
    st.caption(f"{len(apps):,} applications. Each case number is DOL's own; "
               "the source column links to the DOL file it came from.")
    st.dataframe(
        table(apps, ["case_number", "case_status", "visa_class", "fein", "source_file", "dol_file_url"],
              {"case_number": "Case number", "case_status": "Status", "visa_class": "Visa",
               "fein": "Tax ID", "source_file": "DOL file", "dol_file_url": "Source"}),
        column_config={"Source": st.column_config.LinkColumn(display_text="DOL file")},
        hide_index=True, width="stretch")

    with st.expander("Where this page's data comes from"):
        st.markdown(f"Employer row: `{e['source_file']}` (sha256 `{e['source_sha256'][:12]}…`, "
                    f"built {e['source_created_utc']}) from {e['source_urls'].replace(';', ', ')}")
        st.dataframe(pd.DataFrame(q.sources(con)), hide_index=True, width="stretch")


def main():
    try:
        con = db()
    except (OSError, ValueError) as err:  # no database, or its download failed
        st.error(str(err))
        return
    employer_id = st.query_params.get("employer")
    if employer_id and employer_id.isdigit():
        employer_view(con, int(employer_id))
    else:
        search_view(con)


main()
