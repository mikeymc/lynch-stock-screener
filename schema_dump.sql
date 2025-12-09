--
-- PostgreSQL database dump
--

\restrict xtzsoW3oLC4683s4qTvDUSawB667QDSGfnST9jSdGE0DJqTTh99EeYWXdbzdQx7

-- Dumped from database version 16.11
-- Dumped by pg_dump version 16.11 (Homebrew)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: algorithm_configurations; Type: TABLE; Schema: public; Owner: lynch
--

CREATE TABLE public.algorithm_configurations (
    id integer NOT NULL,
    name text,
    weight_peg real,
    weight_consistency real,
    weight_debt real,
    weight_ownership real,
    correlation_1yr real,
    correlation_3yr real,
    correlation_5yr real,
    is_active boolean DEFAULT false,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    peg_excellent real DEFAULT 1.0,
    peg_good real DEFAULT 1.5,
    peg_fair real DEFAULT 2.0,
    debt_excellent real DEFAULT 0.5,
    debt_good real DEFAULT 1.0,
    debt_moderate real DEFAULT 2.0,
    inst_own_min real DEFAULT 0.20,
    inst_own_max real DEFAULT 0.60,
    revenue_growth_excellent real DEFAULT 15.0,
    revenue_growth_good real DEFAULT 10.0,
    revenue_growth_fair real DEFAULT 5.0,
    income_growth_excellent real DEFAULT 15.0,
    income_growth_good real DEFAULT 10.0,
    income_growth_fair real DEFAULT 5.0
);


ALTER TABLE public.algorithm_configurations OWNER TO lynch;

--
-- Name: algorithm_configurations_id_seq; Type: SEQUENCE; Schema: public; Owner: lynch
--

CREATE SEQUENCE public.algorithm_configurations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.algorithm_configurations_id_seq OWNER TO lynch;

--
-- Name: algorithm_configurations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: lynch
--

ALTER SEQUENCE public.algorithm_configurations_id_seq OWNED BY public.algorithm_configurations.id;


--
-- Name: app_settings; Type: TABLE; Schema: public; Owner: lynch
--

CREATE TABLE public.app_settings (
    key text NOT NULL,
    value text,
    description text
);


ALTER TABLE public.app_settings OWNER TO lynch;

--
-- Name: background_jobs; Type: TABLE; Schema: public; Owner: lynch
--

CREATE TABLE public.background_jobs (
    id integer NOT NULL,
    job_type text NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    claimed_by text,
    claimed_at timestamp without time zone,
    claim_expires_at timestamp without time zone,
    params jsonb DEFAULT '{}'::jsonb NOT NULL,
    progress_pct integer DEFAULT 0,
    progress_message text,
    processed_count integer DEFAULT 0,
    total_count integer DEFAULT 0,
    result jsonb,
    error_message text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    started_at timestamp without time zone,
    completed_at timestamp without time zone
);


ALTER TABLE public.background_jobs OWNER TO lynch;

--
-- Name: background_jobs_id_seq; Type: SEQUENCE; Schema: public; Owner: lynch
--

CREATE SEQUENCE public.background_jobs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.background_jobs_id_seq OWNER TO lynch;

--
-- Name: background_jobs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: lynch
--

ALTER SEQUENCE public.background_jobs_id_seq OWNED BY public.background_jobs.id;


--
-- Name: backtest_results; Type: TABLE; Schema: public; Owner: lynch
--

CREATE TABLE public.backtest_results (
    id integer NOT NULL,
    symbol text,
    backtest_date date,
    years_back integer,
    start_price real,
    end_price real,
    total_return real,
    historical_score real,
    historical_rating text,
    peg_score real,
    debt_score real,
    ownership_score real,
    consistency_score real,
    peg_ratio real,
    earnings_cagr real,
    revenue_cagr real,
    debt_to_equity real,
    institutional_ownership real,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.backtest_results OWNER TO lynch;

--
-- Name: backtest_results_id_seq; Type: SEQUENCE; Schema: public; Owner: lynch
--

CREATE SEQUENCE public.backtest_results_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.backtest_results_id_seq OWNER TO lynch;

--
-- Name: backtest_results_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: lynch
--

ALTER SEQUENCE public.backtest_results_id_seq OWNED BY public.backtest_results.id;


--
-- Name: chart_analyses; Type: TABLE; Schema: public; Owner: lynch
--

CREATE TABLE public.chart_analyses (
    symbol text NOT NULL,
    section text NOT NULL,
    analysis_text text,
    generated_at timestamp without time zone,
    model_version text
);


ALTER TABLE public.chart_analyses OWNER TO lynch;

--
-- Name: company_facts; Type: TABLE; Schema: public; Owner: lynch
--

CREATE TABLE public.company_facts (
    cik text NOT NULL,
    entity_name text,
    ticker text,
    facts jsonb NOT NULL,
    last_updated timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.company_facts OWNER TO lynch;

--
-- Name: conversations; Type: TABLE; Schema: public; Owner: lynch
--

CREATE TABLE public.conversations (
    id integer NOT NULL,
    symbol text NOT NULL,
    title text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.conversations OWNER TO lynch;

--
-- Name: conversations_id_seq; Type: SEQUENCE; Schema: public; Owner: lynch
--

CREATE SEQUENCE public.conversations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.conversations_id_seq OWNER TO lynch;

--
-- Name: conversations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: lynch
--

ALTER SEQUENCE public.conversations_id_seq OWNED BY public.conversations.id;


--
-- Name: earnings_history; Type: TABLE; Schema: public; Owner: lynch
--

CREATE TABLE public.earnings_history (
    id integer NOT NULL,
    symbol text,
    year integer,
    earnings_per_share real,
    revenue real,
    fiscal_end text,
    debt_to_equity real,
    period text DEFAULT 'annual'::text,
    net_income real,
    dividend_amount real,
    dividend_yield real,
    operating_cash_flow real,
    capital_expenditures real,
    free_cash_flow real,
    last_updated timestamp without time zone
);


ALTER TABLE public.earnings_history OWNER TO lynch;

--
-- Name: earnings_history_id_seq; Type: SEQUENCE; Schema: public; Owner: lynch
--

CREATE SEQUENCE public.earnings_history_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.earnings_history_id_seq OWNER TO lynch;

--
-- Name: earnings_history_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: lynch
--

ALTER SEQUENCE public.earnings_history_id_seq OWNED BY public.earnings_history.id;


--
-- Name: filing_sections; Type: TABLE; Schema: public; Owner: lynch
--

CREATE TABLE public.filing_sections (
    id integer NOT NULL,
    symbol text,
    section_name text,
    content text,
    filing_type text,
    filing_date text,
    last_updated timestamp without time zone
);


ALTER TABLE public.filing_sections OWNER TO lynch;

--
-- Name: filing_sections_id_seq; Type: SEQUENCE; Schema: public; Owner: lynch
--

CREATE SEQUENCE public.filing_sections_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.filing_sections_id_seq OWNER TO lynch;

--
-- Name: filing_sections_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: lynch
--

ALTER SEQUENCE public.filing_sections_id_seq OWNED BY public.filing_sections.id;


--
-- Name: lynch_analyses; Type: TABLE; Schema: public; Owner: lynch
--

CREATE TABLE public.lynch_analyses (
    symbol text NOT NULL,
    analysis_text text,
    generated_at timestamp without time zone,
    model_version text
);


ALTER TABLE public.lynch_analyses OWNER TO lynch;

--
-- Name: material_events; Type: TABLE; Schema: public; Owner: lynch
--

CREATE TABLE public.material_events (
    id integer NOT NULL,
    symbol text NOT NULL,
    event_type text NOT NULL,
    headline text NOT NULL,
    description text,
    source text DEFAULT 'SEC'::text NOT NULL,
    url text,
    filing_date date,
    datetime integer,
    published_date timestamp without time zone,
    sec_accession_number text,
    sec_item_codes text[],
    last_updated timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    content_text text
);


ALTER TABLE public.material_events OWNER TO lynch;

--
-- Name: material_events_id_seq; Type: SEQUENCE; Schema: public; Owner: lynch
--

CREATE SEQUENCE public.material_events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.material_events_id_seq OWNER TO lynch;

--
-- Name: material_events_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: lynch
--

ALTER SEQUENCE public.material_events_id_seq OWNED BY public.material_events.id;


--
-- Name: message_sources; Type: TABLE; Schema: public; Owner: lynch
--

CREATE TABLE public.message_sources (
    id integer NOT NULL,
    message_id integer NOT NULL,
    section_name text NOT NULL,
    filing_type text,
    filing_date text
);


ALTER TABLE public.message_sources OWNER TO lynch;

--
-- Name: message_sources_id_seq; Type: SEQUENCE; Schema: public; Owner: lynch
--

CREATE SEQUENCE public.message_sources_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.message_sources_id_seq OWNER TO lynch;

--
-- Name: message_sources_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: lynch
--

ALTER SEQUENCE public.message_sources_id_seq OWNED BY public.message_sources.id;


--
-- Name: messages; Type: TABLE; Schema: public; Owner: lynch
--

CREATE TABLE public.messages (
    id integer NOT NULL,
    conversation_id integer NOT NULL,
    role text NOT NULL,
    content text NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.messages OWNER TO lynch;

--
-- Name: messages_id_seq; Type: SEQUENCE; Schema: public; Owner: lynch
--

CREATE SEQUENCE public.messages_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.messages_id_seq OWNER TO lynch;

--
-- Name: messages_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: lynch
--

ALTER SEQUENCE public.messages_id_seq OWNED BY public.messages.id;


--
-- Name: news_articles; Type: TABLE; Schema: public; Owner: lynch
--

CREATE TABLE public.news_articles (
    id integer NOT NULL,
    symbol text NOT NULL,
    finnhub_id integer,
    headline text,
    summary text,
    source text,
    url text,
    image_url text,
    category text,
    datetime integer,
    published_date timestamp without time zone,
    last_updated timestamp without time zone
);


ALTER TABLE public.news_articles OWNER TO lynch;

--
-- Name: news_articles_id_seq; Type: SEQUENCE; Schema: public; Owner: lynch
--

CREATE SEQUENCE public.news_articles_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.news_articles_id_seq OWNER TO lynch;

--
-- Name: news_articles_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: lynch
--

ALTER SEQUENCE public.news_articles_id_seq OWNED BY public.news_articles.id;


--
-- Name: optimization_runs; Type: TABLE; Schema: public; Owner: lynch
--

CREATE TABLE public.optimization_runs (
    id integer NOT NULL,
    years_back integer,
    iterations integer,
    initial_correlation real,
    final_correlation real,
    improvement real,
    best_config_id integer,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.optimization_runs OWNER TO lynch;

--
-- Name: optimization_runs_id_seq; Type: SEQUENCE; Schema: public; Owner: lynch
--

CREATE SEQUENCE public.optimization_runs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.optimization_runs_id_seq OWNER TO lynch;

--
-- Name: optimization_runs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: lynch
--

ALTER SEQUENCE public.optimization_runs_id_seq OWNED BY public.optimization_runs.id;


--
-- Name: price_history; Type: TABLE; Schema: public; Owner: lynch
--

CREATE TABLE public.price_history (
    symbol text NOT NULL,
    date date NOT NULL,
    close real,
    adjusted_close real,
    volume bigint
);


ALTER TABLE public.price_history OWNER TO lynch;

--
-- Name: screening_results; Type: TABLE; Schema: public; Owner: lynch
--

CREATE TABLE public.screening_results (
    id integer NOT NULL,
    session_id integer,
    symbol text,
    company_name text,
    country text,
    market_cap real,
    sector text,
    ipo_year integer,
    price real,
    pe_ratio real,
    peg_ratio real,
    debt_to_equity real,
    institutional_ownership real,
    dividend_yield real,
    earnings_cagr real,
    revenue_cagr real,
    consistency_score real,
    peg_status text,
    peg_score real,
    debt_status text,
    debt_score real,
    institutional_ownership_status text,
    institutional_ownership_score real,
    overall_status text,
    overall_score real,
    scored_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.screening_results OWNER TO lynch;

--
-- Name: screening_results_id_seq; Type: SEQUENCE; Schema: public; Owner: lynch
--

CREATE SEQUENCE public.screening_results_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.screening_results_id_seq OWNER TO lynch;

--
-- Name: screening_results_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: lynch
--

ALTER SEQUENCE public.screening_results_id_seq OWNED BY public.screening_results.id;


--
-- Name: screening_sessions; Type: TABLE; Schema: public; Owner: lynch
--

CREATE TABLE public.screening_sessions (
    id integer NOT NULL,
    created_at timestamp without time zone,
    total_analyzed integer,
    pass_count integer,
    close_count integer,
    fail_count integer,
    status text DEFAULT 'running'::text,
    processed_count integer DEFAULT 0,
    total_count integer DEFAULT 0,
    current_symbol text,
    algorithm text
);


ALTER TABLE public.screening_sessions OWNER TO lynch;

--
-- Name: screening_sessions_id_seq; Type: SEQUENCE; Schema: public; Owner: lynch
--

CREATE SEQUENCE public.screening_sessions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.screening_sessions_id_seq OWNER TO lynch;

--
-- Name: screening_sessions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: lynch
--

ALTER SEQUENCE public.screening_sessions_id_seq OWNED BY public.screening_sessions.id;


--
-- Name: sec_filings; Type: TABLE; Schema: public; Owner: lynch
--

CREATE TABLE public.sec_filings (
    id integer NOT NULL,
    symbol text,
    filing_type text,
    filing_date text,
    document_url text,
    accession_number text,
    last_updated timestamp without time zone
);


ALTER TABLE public.sec_filings OWNER TO lynch;

--
-- Name: sec_filings_id_seq; Type: SEQUENCE; Schema: public; Owner: lynch
--

CREATE SEQUENCE public.sec_filings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.sec_filings_id_seq OWNER TO lynch;

--
-- Name: sec_filings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: lynch
--

ALTER SEQUENCE public.sec_filings_id_seq OWNED BY public.sec_filings.id;


--
-- Name: stock_metrics; Type: TABLE; Schema: public; Owner: lynch
--

CREATE TABLE public.stock_metrics (
    symbol text NOT NULL,
    price real,
    pe_ratio real,
    market_cap real,
    debt_to_equity real,
    institutional_ownership real,
    revenue real,
    dividend_yield real,
    last_updated timestamp without time zone,
    beta real,
    total_debt real,
    interest_expense real,
    effective_tax_rate real
);


ALTER TABLE public.stock_metrics OWNER TO lynch;

--
-- Name: stocks; Type: TABLE; Schema: public; Owner: lynch
--

CREATE TABLE public.stocks (
    symbol text NOT NULL,
    company_name text,
    exchange text,
    sector text,
    country text,
    ipo_year integer,
    last_updated timestamp without time zone
);


ALTER TABLE public.stocks OWNER TO lynch;

--
-- Name: symbol_cache; Type: TABLE; Schema: public; Owner: lynch
--

CREATE TABLE public.symbol_cache (
    id integer NOT NULL,
    symbols text,
    last_updated timestamp without time zone
);


ALTER TABLE public.symbol_cache OWNER TO lynch;

--
-- Name: watchlist; Type: TABLE; Schema: public; Owner: lynch
--

CREATE TABLE public.watchlist (
    symbol text NOT NULL,
    added_at timestamp without time zone
);


ALTER TABLE public.watchlist OWNER TO lynch;

--
-- Name: algorithm_configurations id; Type: DEFAULT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.algorithm_configurations ALTER COLUMN id SET DEFAULT nextval('public.algorithm_configurations_id_seq'::regclass);


--
-- Name: background_jobs id; Type: DEFAULT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.background_jobs ALTER COLUMN id SET DEFAULT nextval('public.background_jobs_id_seq'::regclass);


--
-- Name: backtest_results id; Type: DEFAULT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.backtest_results ALTER COLUMN id SET DEFAULT nextval('public.backtest_results_id_seq'::regclass);


--
-- Name: conversations id; Type: DEFAULT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.conversations ALTER COLUMN id SET DEFAULT nextval('public.conversations_id_seq'::regclass);


--
-- Name: earnings_history id; Type: DEFAULT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.earnings_history ALTER COLUMN id SET DEFAULT nextval('public.earnings_history_id_seq'::regclass);


--
-- Name: filing_sections id; Type: DEFAULT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.filing_sections ALTER COLUMN id SET DEFAULT nextval('public.filing_sections_id_seq'::regclass);


--
-- Name: material_events id; Type: DEFAULT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.material_events ALTER COLUMN id SET DEFAULT nextval('public.material_events_id_seq'::regclass);


--
-- Name: message_sources id; Type: DEFAULT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.message_sources ALTER COLUMN id SET DEFAULT nextval('public.message_sources_id_seq'::regclass);


--
-- Name: messages id; Type: DEFAULT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.messages ALTER COLUMN id SET DEFAULT nextval('public.messages_id_seq'::regclass);


--
-- Name: news_articles id; Type: DEFAULT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.news_articles ALTER COLUMN id SET DEFAULT nextval('public.news_articles_id_seq'::regclass);


--
-- Name: optimization_runs id; Type: DEFAULT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.optimization_runs ALTER COLUMN id SET DEFAULT nextval('public.optimization_runs_id_seq'::regclass);


--
-- Name: screening_results id; Type: DEFAULT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.screening_results ALTER COLUMN id SET DEFAULT nextval('public.screening_results_id_seq'::regclass);


--
-- Name: screening_sessions id; Type: DEFAULT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.screening_sessions ALTER COLUMN id SET DEFAULT nextval('public.screening_sessions_id_seq'::regclass);


--
-- Name: sec_filings id; Type: DEFAULT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.sec_filings ALTER COLUMN id SET DEFAULT nextval('public.sec_filings_id_seq'::regclass);


--
-- Name: algorithm_configurations algorithm_configurations_pkey; Type: CONSTRAINT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.algorithm_configurations
    ADD CONSTRAINT algorithm_configurations_pkey PRIMARY KEY (id);


--
-- Name: app_settings app_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.app_settings
    ADD CONSTRAINT app_settings_pkey PRIMARY KEY (key);


--
-- Name: background_jobs background_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.background_jobs
    ADD CONSTRAINT background_jobs_pkey PRIMARY KEY (id);


--
-- Name: backtest_results backtest_results_pkey; Type: CONSTRAINT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.backtest_results
    ADD CONSTRAINT backtest_results_pkey PRIMARY KEY (id);


--
-- Name: backtest_results backtest_results_symbol_years_back_key; Type: CONSTRAINT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.backtest_results
    ADD CONSTRAINT backtest_results_symbol_years_back_key UNIQUE (symbol, years_back);


--
-- Name: chart_analyses chart_analyses_pkey; Type: CONSTRAINT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.chart_analyses
    ADD CONSTRAINT chart_analyses_pkey PRIMARY KEY (symbol, section);


--
-- Name: company_facts company_facts_pkey; Type: CONSTRAINT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.company_facts
    ADD CONSTRAINT company_facts_pkey PRIMARY KEY (cik);


--
-- Name: conversations conversations_pkey; Type: CONSTRAINT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.conversations
    ADD CONSTRAINT conversations_pkey PRIMARY KEY (id);


--
-- Name: earnings_history earnings_history_pkey; Type: CONSTRAINT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.earnings_history
    ADD CONSTRAINT earnings_history_pkey PRIMARY KEY (id);


--
-- Name: earnings_history earnings_history_symbol_year_period_key; Type: CONSTRAINT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.earnings_history
    ADD CONSTRAINT earnings_history_symbol_year_period_key UNIQUE (symbol, year, period);


--
-- Name: filing_sections filing_sections_pkey; Type: CONSTRAINT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.filing_sections
    ADD CONSTRAINT filing_sections_pkey PRIMARY KEY (id);


--
-- Name: filing_sections filing_sections_symbol_section_name_filing_type_key; Type: CONSTRAINT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.filing_sections
    ADD CONSTRAINT filing_sections_symbol_section_name_filing_type_key UNIQUE (symbol, section_name, filing_type);


--
-- Name: lynch_analyses lynch_analyses_pkey; Type: CONSTRAINT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.lynch_analyses
    ADD CONSTRAINT lynch_analyses_pkey PRIMARY KEY (symbol);


--
-- Name: material_events material_events_pkey; Type: CONSTRAINT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.material_events
    ADD CONSTRAINT material_events_pkey PRIMARY KEY (id);


--
-- Name: material_events material_events_symbol_sec_accession_number_key; Type: CONSTRAINT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.material_events
    ADD CONSTRAINT material_events_symbol_sec_accession_number_key UNIQUE (symbol, sec_accession_number);


--
-- Name: message_sources message_sources_pkey; Type: CONSTRAINT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.message_sources
    ADD CONSTRAINT message_sources_pkey PRIMARY KEY (id);


--
-- Name: messages messages_pkey; Type: CONSTRAINT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_pkey PRIMARY KEY (id);


--
-- Name: news_articles news_articles_pkey; Type: CONSTRAINT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.news_articles
    ADD CONSTRAINT news_articles_pkey PRIMARY KEY (id);


--
-- Name: news_articles news_articles_symbol_finnhub_id_key; Type: CONSTRAINT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.news_articles
    ADD CONSTRAINT news_articles_symbol_finnhub_id_key UNIQUE (symbol, finnhub_id);


--
-- Name: optimization_runs optimization_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.optimization_runs
    ADD CONSTRAINT optimization_runs_pkey PRIMARY KEY (id);


--
-- Name: price_history price_history_pkey; Type: CONSTRAINT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.price_history
    ADD CONSTRAINT price_history_pkey PRIMARY KEY (symbol, date);


--
-- Name: screening_results screening_results_pkey; Type: CONSTRAINT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.screening_results
    ADD CONSTRAINT screening_results_pkey PRIMARY KEY (id);


--
-- Name: screening_sessions screening_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.screening_sessions
    ADD CONSTRAINT screening_sessions_pkey PRIMARY KEY (id);


--
-- Name: sec_filings sec_filings_pkey; Type: CONSTRAINT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.sec_filings
    ADD CONSTRAINT sec_filings_pkey PRIMARY KEY (id);


--
-- Name: sec_filings sec_filings_symbol_accession_number_key; Type: CONSTRAINT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.sec_filings
    ADD CONSTRAINT sec_filings_symbol_accession_number_key UNIQUE (symbol, accession_number);


--
-- Name: stock_metrics stock_metrics_pkey; Type: CONSTRAINT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.stock_metrics
    ADD CONSTRAINT stock_metrics_pkey PRIMARY KEY (symbol);


--
-- Name: stocks stocks_pkey; Type: CONSTRAINT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.stocks
    ADD CONSTRAINT stocks_pkey PRIMARY KEY (symbol);


--
-- Name: symbol_cache symbol_cache_pkey; Type: CONSTRAINT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.symbol_cache
    ADD CONSTRAINT symbol_cache_pkey PRIMARY KEY (id);


--
-- Name: watchlist watchlist_pkey; Type: CONSTRAINT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.watchlist
    ADD CONSTRAINT watchlist_pkey PRIMARY KEY (symbol);


--
-- Name: idx_background_jobs_pending; Type: INDEX; Schema: public; Owner: lynch
--

CREATE INDEX idx_background_jobs_pending ON public.background_jobs USING btree (status, created_at) WHERE (status = 'pending'::text);


--
-- Name: idx_company_facts_entity_name; Type: INDEX; Schema: public; Owner: lynch
--

CREATE INDEX idx_company_facts_entity_name ON public.company_facts USING btree (entity_name);


--
-- Name: idx_company_facts_facts_gin; Type: INDEX; Schema: public; Owner: lynch
--

CREATE INDEX idx_company_facts_facts_gin ON public.company_facts USING gin (facts);


--
-- Name: idx_company_facts_ticker; Type: INDEX; Schema: public; Owner: lynch
--

CREATE INDEX idx_company_facts_ticker ON public.company_facts USING btree (ticker);


--
-- Name: idx_material_events_accession; Type: INDEX; Schema: public; Owner: lynch
--

CREATE INDEX idx_material_events_accession ON public.material_events USING btree (sec_accession_number);


--
-- Name: idx_material_events_symbol_date; Type: INDEX; Schema: public; Owner: lynch
--

CREATE INDEX idx_material_events_symbol_date ON public.material_events USING btree (symbol, datetime DESC);


--
-- Name: idx_material_events_type; Type: INDEX; Schema: public; Owner: lynch
--

CREATE INDEX idx_material_events_type ON public.material_events USING btree (event_type);


--
-- Name: chart_analyses chart_analyses_symbol_fkey; Type: FK CONSTRAINT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.chart_analyses
    ADD CONSTRAINT chart_analyses_symbol_fkey FOREIGN KEY (symbol) REFERENCES public.stocks(symbol);


--
-- Name: conversations conversations_symbol_fkey; Type: FK CONSTRAINT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.conversations
    ADD CONSTRAINT conversations_symbol_fkey FOREIGN KEY (symbol) REFERENCES public.stocks(symbol);


--
-- Name: earnings_history earnings_history_symbol_fkey; Type: FK CONSTRAINT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.earnings_history
    ADD CONSTRAINT earnings_history_symbol_fkey FOREIGN KEY (symbol) REFERENCES public.stocks(symbol);


--
-- Name: filing_sections filing_sections_symbol_fkey; Type: FK CONSTRAINT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.filing_sections
    ADD CONSTRAINT filing_sections_symbol_fkey FOREIGN KEY (symbol) REFERENCES public.stocks(symbol);


--
-- Name: lynch_analyses lynch_analyses_symbol_fkey; Type: FK CONSTRAINT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.lynch_analyses
    ADD CONSTRAINT lynch_analyses_symbol_fkey FOREIGN KEY (symbol) REFERENCES public.stocks(symbol);


--
-- Name: material_events material_events_symbol_fkey; Type: FK CONSTRAINT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.material_events
    ADD CONSTRAINT material_events_symbol_fkey FOREIGN KEY (symbol) REFERENCES public.stocks(symbol);


--
-- Name: message_sources message_sources_message_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.message_sources
    ADD CONSTRAINT message_sources_message_id_fkey FOREIGN KEY (message_id) REFERENCES public.messages(id) ON DELETE CASCADE;


--
-- Name: messages messages_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.conversations(id) ON DELETE CASCADE;


--
-- Name: news_articles news_articles_symbol_fkey; Type: FK CONSTRAINT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.news_articles
    ADD CONSTRAINT news_articles_symbol_fkey FOREIGN KEY (symbol) REFERENCES public.stocks(symbol);


--
-- Name: optimization_runs optimization_runs_best_config_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.optimization_runs
    ADD CONSTRAINT optimization_runs_best_config_id_fkey FOREIGN KEY (best_config_id) REFERENCES public.algorithm_configurations(id);


--
-- Name: price_history price_history_symbol_fkey; Type: FK CONSTRAINT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.price_history
    ADD CONSTRAINT price_history_symbol_fkey FOREIGN KEY (symbol) REFERENCES public.stocks(symbol);


--
-- Name: screening_results screening_results_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.screening_results
    ADD CONSTRAINT screening_results_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.screening_sessions(id) ON DELETE CASCADE;


--
-- Name: sec_filings sec_filings_symbol_fkey; Type: FK CONSTRAINT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.sec_filings
    ADD CONSTRAINT sec_filings_symbol_fkey FOREIGN KEY (symbol) REFERENCES public.stocks(symbol);


--
-- Name: stock_metrics stock_metrics_symbol_fkey; Type: FK CONSTRAINT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.stock_metrics
    ADD CONSTRAINT stock_metrics_symbol_fkey FOREIGN KEY (symbol) REFERENCES public.stocks(symbol);


--
-- Name: watchlist watchlist_symbol_fkey; Type: FK CONSTRAINT; Schema: public; Owner: lynch
--

ALTER TABLE ONLY public.watchlist
    ADD CONSTRAINT watchlist_symbol_fkey FOREIGN KEY (symbol) REFERENCES public.stocks(symbol);


--
-- PostgreSQL database dump complete
--

\unrestrict xtzsoW3oLC4683s4qTvDUSawB667QDSGfnST9jSdGE0DJqTTh99EeYWXdbzdQx7

