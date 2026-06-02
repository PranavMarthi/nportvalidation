"""N-PORT XML generator using lxml.

Builds a complete edgarSubmission XML document from FundConfig,
FilingData, and a list of Holdings. The output must match the
SEC's N-PORT XSD schema v1.13 exactly.
"""

import json

from lxml import etree
from lxml.etree import SubElement

from nport.constants import NS_NPORT, NS_NPORTCOMMON, NSMAP
from nport.models import FilingData, FundConfig, Holding


class NportBuilder:
    def __init__(
        self,
        config: FundConfig,
        filing: FilingData,
        holdings: list[Holding],
    ):
        self.config = config
        self.filing = filing
        self.holdings = holdings

    def build(self) -> etree._Element:
        """Build the complete edgarSubmission element tree."""
        root = etree.Element(f"{{{NS_NPORT}}}edgarSubmission", nsmap=NSMAP)
        self._build_header(root)
        form = SubElement(root, "formData")
        self._build_gen_info(form)
        self._build_fund_info(form)
        self._build_investments(form)
        self._build_signature(form)
        return root

    def to_xml_bytes(self) -> bytes:
        """Serialize to UTF-8 XML bytes with declaration."""
        root = self.build()
        return etree.tostring(
            root,
            xml_declaration=True,
            encoding="UTF-8",
            pretty_print=True,
        )

    # ── Header ──────────────────────────────────────────────

    def _build_header(self, root: etree._Element) -> None:
        header = SubElement(root, "headerData")
        SubElement(header, "submissionType").text = self.filing.submission_type
        SubElement(header, "isConfidential").text = "false"

        filer_info = SubElement(header, "filerInfo")

        # liveTestFlag is the first child of filerInfo per the schema. Emit only
        # for TEST submissions; EDGAR treats an omitted element as LIVE, which
        # matches how production filings (e.g. our FDRS Dec 2025 reference) are
        # submitted. This makes accidental live submission a deliberate choice.
        if self.filing.live_test_flag == "TEST":
            SubElement(filer_info, "liveTestFlag").text = "TEST"
        elif self.filing.live_test_flag != "LIVE":
            raise ValueError(
                f"liveTestFlag must be 'TEST' or 'LIVE', got {self.filing.live_test_flag!r}"
            )

        filer = SubElement(filer_info, "filer")
        creds = SubElement(filer, "issuerCredentials")
        SubElement(creds, "cik").text = self.config.cik
        SubElement(creds, "ccc").text = self.config.ccc

        series_class = SubElement(filer_info, "seriesClassInfo")
        SubElement(series_class, "seriesId").text = self.config.series_id
        SubElement(series_class, "classId").text = self.config.class_id

    # ── Part A: General Info ────────────────────────────────

    def _build_gen_info(self, form: etree._Element) -> None:
        c = self.config
        f = self.filing
        gi = SubElement(form, "genInfo")

        SubElement(gi, "regName").text = c.reg_name
        SubElement(gi, "regFileNumber").text = c.reg_file_number
        SubElement(gi, "regCik").text = c.reg_cik
        SubElement(gi, "regLei").text = c.reg_lei
        SubElement(gi, "regStreet1").text = c.reg_street1
        if c.reg_street2:
            SubElement(gi, "regStreet2").text = c.reg_street2
        SubElement(gi, "regCity").text = c.reg_city

        # regStateConditional: self-closing element with attributes
        SubElement(
            gi,
            "regStateConditional",
            attrib={"regCountry": c.reg_country, "regState": c.reg_state},
        )

        SubElement(gi, "regZipOrPostalCode").text = c.reg_zip
        SubElement(gi, "regPhone").text = c.reg_phone
        SubElement(gi, "seriesName").text = c.series_name
        SubElement(gi, "seriesId").text = c.series_id
        SubElement(gi, "seriesLei").text = c.series_lei
        SubElement(gi, "repPdEnd").text = f.rep_pd_end
        SubElement(gi, "repPdDate").text = f.rep_pd_date
        SubElement(gi, "isFinalFiling").text = f.is_final_filing

    # ── Part B: Fund Info ───────────────────────────────────

    def _build_fund_info(self, form: etree._Element) -> None:
        f = self.filing
        c = self.config
        fi = SubElement(form, "fundInfo")

        SubElement(fi, "totAssets").text = f.tot_assets
        SubElement(fi, "totLiabs").text = f.tot_liabs
        SubElement(fi, "netAssets").text = f.net_assets

        # Balance sheet items
        SubElement(fi, "assetsAttrMiscSec").text = f.assets_attr_misc_sec
        SubElement(fi, "assetsInvested").text = f.assets_invested
        SubElement(fi, "amtPayOneYrBanksBorr").text = f.amt_pay_one_yr_banks_borr
        SubElement(fi, "amtPayOneYrCtrldComp").text = f.amt_pay_one_yr_ctrld_comp
        SubElement(fi, "amtPayOneYrOthAffil").text = f.amt_pay_one_yr_oth_affil
        SubElement(fi, "amtPayOneYrOther").text = f.amt_pay_one_yr_other
        SubElement(fi, "amtPayAftOneYrBanksBorr").text = f.amt_pay_aft_one_yr_banks_borr
        SubElement(fi, "amtPayAftOneYrCtrldComp").text = f.amt_pay_aft_one_yr_ctrld_comp
        SubElement(fi, "amtPayAftOneYrOthAffil").text = f.amt_pay_aft_one_yr_oth_affil
        SubElement(fi, "amtPayAftOneYrOther").text = f.amt_pay_aft_one_yr_other
        SubElement(fi, "delayDeliv").text = f.delay_deliv
        SubElement(fi, "standByCommit").text = f.stand_by_commit
        SubElement(fi, "liquidPref").text = f.liquid_pref

        # B.3 Risk metrics (optional, before isNonCashCollateral per XSD)
        if f.cur_metrics_json:
            self._build_risk_metrics(fi, f)

        # Securities lending (fund-level)
        SubElement(fi, "isNonCashCollateral").text = f.is_non_cash_collateral

        # Return info
        ri = SubElement(fi, "returnInfo")
        mtr = SubElement(ri, "monthlyTotReturns")
        SubElement(
            mtr,
            "monthlyTotReturn",
            attrib={
                "classId": c.class_id,
                "rtn1": f.rtn1,
                "rtn2": f.rtn2,
                "rtn3": f.rtn3,
            },
        )
        SubElement(
            ri,
            "othMon1",
            attrib={
                "netRealizedGain": f.net_realized_gain_mon1,
                "netUnrealizedAppr": f.net_unrealized_appr_mon1,
            },
        )
        SubElement(
            ri,
            "othMon2",
            attrib={
                "netRealizedGain": f.net_realized_gain_mon2,
                "netUnrealizedAppr": f.net_unrealized_appr_mon2,
            },
        )
        SubElement(
            ri,
            "othMon3",
            attrib={
                "netRealizedGain": f.net_realized_gain_mon3,
                "netUnrealizedAppr": f.net_unrealized_appr_mon3,
            },
        )

        # Flow info
        SubElement(
            fi,
            "mon1Flow",
            attrib={
                "redemption": f.mon1_redemption,
                "reinvestment": f.mon1_reinvestment,
                "sales": f.mon1_sales,
            },
        )
        SubElement(
            fi,
            "mon2Flow",
            attrib={
                "redemption": f.mon2_redemption,
                "reinvestment": f.mon2_reinvestment,
                "sales": f.mon2_sales,
            },
        )
        SubElement(
            fi,
            "mon3Flow",
            attrib={
                "redemption": f.mon3_redemption,
                "reinvestment": f.mon3_reinvestment,
                "sales": f.mon3_sales,
            },
        )

        # VaR info (varInfo block matches reference filing pattern)
        var_info = SubElement(fi, "varInfo")
        fdi = SubElement(var_info, "fundsDesignatedInfo")
        SubElement(fdi, "nameDesignatedIndex").text = f.name_designated_index
        SubElement(fdi, "indexIdentifier").text = f.index_identifier

    # XSD period attribute names for risk metrics
    _RISK_PERIODS = ["period3Mon", "period1Yr", "period5Yr", "period10Yr", "period30Yr"]
    # Input key suffixes mapping to XSD attribute names
    _RISK_PERIOD_KEYS = ["3month", "1year", "5year", "10year", "30year"]

    def _build_risk_metrics(self, fi: etree._Element, f: FilingData) -> None:
        """Emit B.3 interest rate / credit spread risk metrics.

        XSD: intrstRtRiskdv01/dv100 are self-closing with period attributes.
        creditSprdRisk* are always emitted (both) when curMetrics is present.
        """
        metrics = json.loads(f.cur_metrics_json)
        cur_metrics = SubElement(fi, "curMetrics")
        for m in metrics:
            cm = SubElement(cur_metrics, "curMetric")
            SubElement(cm, "curCd").text = m["curCd"]
            # intrstRtRiskdv01 — self-closing with period attributes
            SubElement(cm, "intrstRtRiskdv01", attrib={
                p: m.get(f"dv01_{k}", "0")
                for p, k in zip(self._RISK_PERIODS, self._RISK_PERIOD_KEYS)
            })
            # intrstRtRiskdv100 — self-closing with period attributes
            SubElement(cm, "intrstRtRiskdv100", attrib={
                p: m.get(f"dv100_{k}", "0")
                for p, k in zip(self._RISK_PERIODS, self._RISK_PERIOD_KEYS)
            })

        # Both credit spread elements are REQUIRED when curMetrics is present
        ig = json.loads(f.credit_sprd_risk_ig_json) if f.credit_sprd_risk_ig_json else {}
        SubElement(fi, "creditSprdRiskInvstGrade", attrib={
            p: ig.get(k, "0")
            for p, k in zip(self._RISK_PERIODS, self._RISK_PERIOD_KEYS)
        })
        nig = json.loads(f.credit_sprd_risk_nonig_json) if f.credit_sprd_risk_nonig_json else {}
        SubElement(fi, "creditSprdRiskNonInvstGrade", attrib={
            p: nig.get(k, "0")
            for p, k in zip(self._RISK_PERIODS, self._RISK_PERIOD_KEYS)
        })

    # ── Part C: Investments / Securities ────────────────────

    def _build_investments(self, form: etree._Element) -> None:
        inv_secs = SubElement(form, "invstOrSecs")
        for holding in self.holdings:
            self._build_one_holding(inv_secs, holding)

    def _build_one_holding(
        self, parent: etree._Element, h: Holding
    ) -> None:
        sec = SubElement(parent, "invstOrSec")

        SubElement(sec, "name").text = h.name
        SubElement(sec, "lei").text = h.lei
        SubElement(sec, "title").text = h.title
        SubElement(sec, "cusip").text = h.cusip

        # Identifiers
        ids = SubElement(sec, "identifiers")
        if h.isin:
            SubElement(ids, "isin", attrib={"value": h.isin})
        if h.ticker:
            SubElement(ids, "ticker", attrib={"value": h.ticker})
        if h.other_desc:
            SubElement(ids, "other", attrib={
                "otherDesc": h.other_desc,
                "value": h.other_value,
            })

        SubElement(sec, "balance").text = h.balance
        SubElement(sec, "units").text = h.units

        # Currency: currencyConditional (with exchange rate) or curCd
        if h.exchange_rt:
            SubElement(sec, "currencyConditional", attrib={
                "curCd": h.cur_cd,
                "exchangeRt": h.exchange_rt,
            })
        else:
            SubElement(sec, "curCd").text = h.cur_cd

        SubElement(sec, "valUSD").text = h.val_usd
        SubElement(sec, "pctVal").text = h.pct_val
        SubElement(sec, "payoffProfile").text = h.payoff_profile

        # Asset category: assetConditional or assetCat
        if h.asset_conditional_desc:
            SubElement(sec, "assetConditional", attrib={
                "desc": h.asset_conditional_desc,
                "assetCat": h.asset_cat,
            })
        else:
            SubElement(sec, "assetCat").text = h.asset_cat

        # Issuer category: issuerConditional or issuerCat
        if h.issuer_conditional_desc:
            SubElement(sec, "issuerConditional", attrib={
                "desc": h.issuer_conditional_desc,
                "issuerCat": h.issuer_cat,
            })
        else:
            SubElement(sec, "issuerCat").text = h.issuer_cat

        SubElement(sec, "invCountry").text = h.inv_country
        SubElement(sec, "isRestrictedSec").text = h.is_restricted_sec
        SubElement(sec, "fairValLevel").text = h.fair_val_level

        # Debt securities (C.9)
        if h.maturity_dt:
            self._build_debt_sec(sec, h)

        # Derivative info (C.11)
        if h.deriv_cat:
            self._build_derivative_info(sec, h)

        # Security lending
        sl = SubElement(sec, "securityLending")
        SubElement(sl, "isCashCollateral").text = h.is_cash_collateral
        SubElement(sl, "isNonCashCollateral").text = h.is_non_cash_collateral
        SubElement(sl, "isLoanByFund").text = h.is_loan_by_fund

    # ── Debt Securities (C.9) ──────────────────────────────

    def _build_debt_sec(self, sec: etree._Element, h: Holding) -> None:
        ds = SubElement(sec, "debtSec")
        SubElement(ds, "maturityDt").text = h.maturity_dt
        SubElement(ds, "couponKind").text = h.coupon_kind
        SubElement(ds, "annualizedRt").text = h.annualized_rt
        # XSD requires all three flags (minOccurs=1); default to "N"
        SubElement(ds, "isDefault").text = h.is_default or "N"
        SubElement(ds, "areIntrstPmntsInArrs").text = h.are_intrst_pmnts_in_arrs or "N"
        SubElement(ds, "isPaidKind").text = h.is_paid_kind or "N"

    # ── Derivative Info (C.11) ─────────────────────────────

    def _build_derivative_info(self, sec: etree._Element, h: Holding) -> None:
        di = SubElement(sec, "derivativeInfo")

        if h.deriv_cat in ("OPT", "SWO", "WAR"):
            self._build_option_deriv(di, h)
        elif h.deriv_cat == "SWP":
            self._build_swap_deriv(di, h)
        elif h.deriv_cat in ("FWD", "FUT"):
            self._build_fwd_fut_deriv(di, h)
        else:  # OTH or other
            self._build_other_deriv(di, h)

    def _build_option_deriv(self, di: etree._Element, h: Holding) -> None:
        # Fix 1: derivCat attribute
        opt = SubElement(di, "optionSwaptionWarrantDeriv", attrib={"derivCat": h.deriv_cat})
        # Fix 2: counterparties is the repeating element with direct children
        self._add_counterparty(opt, h)
        SubElement(opt, "putOrCall").text = h.put_or_call
        SubElement(opt, "writtenOrPur").text = h.written_or_pur

        # Reference instrument
        if h.ref_inst_type:
            self._build_ref_instrument(opt, h)

        SubElement(opt, "shareNo").text = h.share_no
        SubElement(opt, "exercisePrice").text = h.exercise_price
        SubElement(opt, "exercisePriceCurCd").text = h.exercise_price_cur_cd or h.cur_cd
        SubElement(opt, "expDt").text = h.exp_dt
        SubElement(opt, "delta").text = h.delta
        SubElement(opt, "unrealizedAppr").text = h.unrealized_appr

    def _build_swap_deriv(self, di: etree._Element, h: Holding) -> None:
        # Fix 1: derivCat attribute
        swap = SubElement(di, "swapDeriv", attrib={"derivCat": "SWP"})
        # Fix 2: counterparties structure
        self._add_counterparty(swap, h)

        # Fix 5: XSD order — descRefInstrmnt before swapFlag
        if h.ref_inst_type:
            self._build_ref_instrument(swap, h)

        SubElement(swap, "swapFlag").text = h.swap_flag or "N"

        # Fix 5: receive leg, then pay leg, then termination/notional
        self._build_swap_legs(swap, h)

        SubElement(swap, "terminationDt").text = h.termination_dt
        SubElement(swap, "upfrontPmnt").text = h.upfront_pmnt or "0"
        SubElement(swap, "pmntCurCd").text = h.pmnt_cur_cd or h.cur_cd
        SubElement(swap, "upfrontRcpt").text = h.upfront_rcpt or "0"
        SubElement(swap, "rcptCurCd").text = h.rcpt_cur_cd or h.cur_cd
        SubElement(swap, "notionalAmt").text = h.notional_amt
        SubElement(swap, "curCd").text = h.swap_cur_cd or h.cur_cd
        SubElement(swap, "unrealizedAppr").text = h.unrealized_appr

    def _build_fwd_fut_deriv(self, di: etree._Element, h: Holding) -> None:
        # Fix 6: correct element names; Fix 1: derivCat attribute
        if h.deriv_cat == "FWD":
            ff = SubElement(di, "fwdDeriv", attrib={"derivCat": "FWD"})
        else:
            ff = SubElement(di, "futrDeriv", attrib={"derivCat": "FUT"})
        # Fix 2: counterparties structure
        self._add_counterparty(ff, h)
        # Fix 6: payOffProf before descRefInstrmnt
        if h.payoff_prof_deriv:
            SubElement(ff, "payOffProf").text = h.payoff_prof_deriv
        if h.ref_inst_type:
            self._build_ref_instrument(ff, h)
        # Fix 6: expDate not expDt
        if h.exp_dt:
            SubElement(ff, "expDate").text = h.exp_dt
        if h.notional_amt:
            SubElement(ff, "notionalAmt").text = h.notional_amt
            SubElement(ff, "curCd").text = h.swap_cur_cd or h.cur_cd
        SubElement(ff, "unrealizedAppr").text = h.unrealized_appr

    def _build_other_deriv(self, di: etree._Element, h: Holding) -> None:
        # Fix 1 + 13: derivCat="OTH" + othDesc attribute
        oth = SubElement(di, "othDeriv", attrib={
            "derivCat": "OTH",
            "othDesc": h.other_deriv_desc or "Other",
        })
        # Fix 2: counterparties structure
        self._add_counterparty(oth, h)
        if h.ref_inst_type:
            self._build_ref_instrument(oth, h)
        if h.termination_dt:
            SubElement(oth, "terminationDt").text = h.termination_dt
        # Fix 13: notionalAmts wrapper with notionalAmt using attributes
        if h.notional_amt:
            na_wrapper = SubElement(oth, "notionalAmts")
            SubElement(na_wrapper, "notionalAmt", attrib={
                "amt": h.notional_amt,
                "curCd": h.swap_cur_cd or h.cur_cd,
            })
        SubElement(oth, "unrealizedAppr").text = h.unrealized_appr

    def _add_counterparty(self, parent: etree._Element, h: Holding) -> None:
        """Fix 2: counterparties IS the repeating element with direct children."""
        cp = SubElement(parent, "counterparties")
        SubElement(cp, "counterpartyName").text = h.counterparty_name
        SubElement(cp, "counterpartyLei").text = h.counterparty_lei

    # ── Reference Instrument ───────────────────────────────

    def _build_ref_instrument(self, parent: etree._Element, h: Holding) -> None:
        desc = SubElement(parent, "descRefInstrmnt")
        if h.ref_inst_type == "indexBasket":
            ib = SubElement(desc, "indexBasketInfo")
            SubElement(ib, "indexName").text = h.ref_index_name
            SubElement(ib, "indexIdentifier").text = h.ref_index_identifier
        else:  # otherRefInst
            ori = SubElement(desc, "otherRefInst")
            SubElement(ori, "issuerName").text = h.ref_issuer_name
            SubElement(ori, "issueTitle").text = h.ref_issue_title
            ids = SubElement(ori, "identifiers")
            if h.ref_cusip:
                SubElement(ids, "cusip", attrib={"value": h.ref_cusip})
            if h.ref_isin:
                SubElement(ids, "isin", attrib={"value": h.ref_isin})
            if h.ref_ticker:
                SubElement(ids, "ticker", attrib={"value": h.ref_ticker})

    # ── Swap Legs ──────────────────────────────────────────

    def _build_swap_legs(self, swap: etree._Element, h: Holding) -> None:
        """Emit receive and pay legs with XSD-compliant attribute-based format."""
        # Receive leg
        if h.rec_fixed_or_floating == "Fixed":
            SubElement(swap, "fixedRecDesc", attrib={
                "fixedOrFloating": "Fixed",
                "fixedRt": h.rec_fixed_rt,
                "curCd": h.rec_cur_cd or h.cur_cd,
                "amount": h.rec_pmnt_amt or "0",
            })
        elif h.rec_fixed_or_floating == "Floating":
            fl = SubElement(swap, "floatingRecDesc", attrib={
                "fixedOrFloating": "Floating",
                "floatingRtIndex": h.rec_floating_rt_index,
                "floatingRtSpread": h.rec_floating_rt_spread,
                "curCd": h.rec_cur_cd or h.cur_cd,
                "pmntAmt": h.rec_pmnt_amt or "0",
            })
            if h.rec_rate_tenor:
                tenors = SubElement(fl, "rtResetTenors")
                SubElement(tenors, "rtResetTenor", attrib={
                    "rateTenor": h.rec_rate_tenor,
                    "rateTenorUnit": h.rec_rate_unit,
                    "resetDt": h.rec_reset_dt or h.rec_rate_tenor,
                    "resetDtUnit": h.rec_reset_unit or h.rec_rate_unit,
                })
        elif h.rec_fixed_or_floating == "Other":
            # Fix 11: fixedOrFloating="Other" attribute
            SubElement(swap, "otherRecDesc", attrib={
                "fixedOrFloating": "Other",
            }).text = h.rec_desc

        # Pay leg
        if h.pmnt_fixed_or_floating == "Fixed":
            SubElement(swap, "fixedPmntDesc", attrib={
                "fixedOrFloating": "Fixed",
                "fixedRt": h.pmnt_fixed_rt,
                "curCd": h.pmnt_cur_cd_leg or h.cur_cd,
                "amount": h.pmnt_pmnt_amt or "0",
            })
        elif h.pmnt_fixed_or_floating == "Floating":
            flp = SubElement(swap, "floatingPmntDesc", attrib={
                "fixedOrFloating": "Floating",
                "floatingRtIndex": h.pmnt_floating_rt_index,
                "floatingRtSpread": h.pmnt_floating_rt_spread,
                "curCd": h.pmnt_cur_cd_leg or h.cur_cd,
                "pmntAmt": h.pmnt_pmnt_amt or "0",
            })
            if h.pmnt_rate_tenor:
                tenors = SubElement(flp, "rtResetTenors")
                SubElement(tenors, "rtResetTenor", attrib={
                    "rateTenor": h.pmnt_rate_tenor,
                    "rateTenorUnit": h.pmnt_rate_unit,
                    "resetDt": h.pmnt_reset_dt or h.pmnt_rate_tenor,
                    "resetDtUnit": h.pmnt_reset_unit or h.pmnt_rate_unit,
                })
        elif h.pmnt_fixed_or_floating == "Other":
            # Fix 11: fixedOrFloating="Other" attribute
            SubElement(swap, "otherPmntDesc", attrib={
                "fixedOrFloating": "Other",
            }).text = h.rec_desc

    # ── Part F: Signature ───────────────────────────────────

    def _build_signature(self, form: etree._Element) -> None:
        c = self.config
        f = self.filing
        sig = SubElement(form, "signature")

        # Signature children use the ncom namespace
        ncom = NS_NPORTCOMMON
        SubElement(sig, f"{{{ncom}}}dateSigned").text = f.date_signed
        SubElement(sig, f"{{{ncom}}}nameOfApplicant").text = c.signer_org
        SubElement(sig, f"{{{ncom}}}signature").text = f"/s/ {c.signer_name}"
        SubElement(sig, f"{{{ncom}}}signerName").text = c.signer_name
        SubElement(sig, f"{{{ncom}}}title").text = c.signer_title
