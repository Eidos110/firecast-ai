"""
Sidebar component for input parameters
"""

import streamlit as st
import pandas as pd
from typing import Dict, Any
import requests
import logging

from frontend.utils.weather_api import get_weather_data
from frontend.utils.gee_data import get_location_data

logger = logging.getLogger(__name__)

VEGETATION_TYPES = {
    "Savana": {"moisture_content": 35, "flammability": 0.8, "ndvi_default": 0.3},
    "Hutan Tropis Lembab": {"moisture_content": 60, "flammability": 0.5, "ndvi_default": 0.75},
    "Semak Kering": {"moisture_content": 20, "flammability": 0.95, "ndvi_default": 0.25},
    "Lahan Gambut": {"moisture_content": 45, "flammability": 0.7, "ndvi_default": 0.55},
    "Padang Rumput": {"moisture_content": 40, "flammability": 0.75, "ndvi_default": 0.4},
    "Hutan Pinus": {"moisture_content": 30, "flammability": 0.85, "ndvi_default": 0.6},
}

# Indonesian locations database — provincial capitals + fire-prone hotspots
INDONESIA_LOCATIONS = {
    # ── Sumatra ──────────────────────────────────────────────────────
    "aceh": {"lat": 5.55, "lon": 95.32, "name": "Aceh"},
    "b. aceh": {"lat": 5.20, "lon": 97.15, "name": "Banda Aceh"},
    "langsa": {"lat": 4.48, "lon": 97.97, "name": "Langsa"},
    "lhokseumawe": {"lat": 5.18, "lon": 97.15, "name": "Lhokseumawe"},
    "simeulue": {"lat": 2.60, "lon": 96.10, "name": "Simeulue"},
    "aceh besar": {"lat": 5.43, "lon": 95.52, "name": "Aceh Besar"},
    "aceh selatan": {"lat": 3.20, "lon": 97.30, "name": "Aceh Selatan"},
    "aceh tamiang": {"lat": 4.30, "lon": 97.90, "name": "Aceh Tamiang"},
    "bener meriah": {"lat": 4.78, "lon": 96.93, "name": "Bener Meriah"},
    "gayo lues": {"lat": 4.00, "lon": 97.35, "name": "Gayo Lues"},
    "nagan raya": {"lat": 4.17, "lon": 96.48, "name": "Nagan Raya"},
    "pidie": {"lat": 4.92, "lon": 96.42, "name": "Pidie"},
    "pidie jaya": {"lat": 4.92, "lon": 96.42, "name": "Pidie Jaya"},
    "p. sidempuan": {"lat": 1.38, "lon": 99.27, "name": "P. Sibolga"},
    "aceh tengah": {"lat": 4.40, "lon": 96.83, "name": "Aceh Tengah"},
    "aceh tenggara": {"lat": 3.40, "lon": 97.75, "name": "Aceh Tenggara"},
    "aceh timur": {"lat": 4.55, "lon": 97.48, "name": "Aceh Timur"},
    "aceh utara": {"lat": 5.10, "lon": 97.35, "name": "Aceh Utara"},
    "p. aceh": {"lat": 5.90, "lon": 95.33, "name": "P. Aceh"},
    "subulussalam": {"lat": 2.65, "lon": 97.93, "name": "Subulussalam"},
    # Sumatra Utara
    "medan": {"lat": 3.59, "lon": 98.67, "name": "Medan"},
    "pematangsiantar": {"lat": 2.96, "lon": 99.07, "name": "Pematangsiantar"},
    "sibolga": {"lat": 1.74, "lon": 98.78, "name": "Sibolga"},
    "tanjung balai": {"lat": 2.97, "lon": 99.80, "name": "Tanjungbalai"},
    "binjai": {"lat": 3.60, "lon": 98.48, "name": "Binjai"},
    "tebing tinggi": {"lat": 3.33, "lon": 99.17, "name": "Tebingtinggi"},
    "asahan": {"lat": 2.80, "lon": 99.13, "name": "Kisaran / Asahan"},
    "labuhanbatu": {"lat": 2.13, "lon": 99.22, "name": "Rantau Prapat"},
    "dairi": {"lat": 2.90, "lon": 98.18, "name": "Sidikalang"},
    "karo": {"lat": 3.14, "lon": 98.24, "name": "Kabanjahe"},
    "langkat": {"lat": 3.84, "lon": 98.19, "name": "Stabat"},
    "mandailing natal": {"lat": 0.80, "lon": 99.25, "name": "Panyabungan"},
    "nias": {"lat": 1.13, "lon": 97.70, "name": "Gunungsitoli"},
    "nias selatan": {"lat": 0.45, "lon": 97.83, "name": "Teluk Dalam"},
    "nias utara": {"lat": 1.30, "lon": 97.35, "name": "Lotu"},
    "padang lawas": {"lat": 1.59, "lon": 99.58, "name": "Sibuhuan"},
    "tapanuli selatan": {"lat": 1.85, "lon": 99.40, "name": "Padang Sidimpuan"},
    "tapanuli tengah": {"lat": 1.93, "lon": 98.79, "name": "Sitelu"},
    "tapanuli utara": {"lat": 2.37, "lon": 98.95, "name": "Tarutung"},
    "humbang hasundutan": {"lat": 2.25, "lon": 98.15, "name": "Dolok Sanggul"},
    "samosir": {"lat": 2.60, "lon": 98.72, "name": "Pangururan"},
    "serdang bedagai": {"lat": 3.37, "lon": 99.05, "name": "Sei Rampah"},
    "simalungun": {"lat": 2.90, "lon": 99.03, "name": "Raya"},
    # Sumatra Barat
    "padang": {"lat": -0.94, "lon": 100.35, "name": "Padang"},
    "padang panjang": {"lat": -0.47, "lon": 100.42, "name": "Padang Panjang"},
    "payakumbuh": {"lat": -0.22, "lon": 100.62, "name": "Payakumbuh"},
    "bukittinggi": {"lat": -0.31, "lon": 100.37, "name": "Bukittinggi"},
    "solok": {"lat": -1.00, "lon": 100.55, "name": "Solok"},
    "sawahlunto": {"lat": -0.68, "lon": 100.83, "name": "Sawahlunto"},
    "pasaman barat": {"lat": 0.20, "lon": 99.45, "name": "Simpang Ampek"},
    "pasaman": {"lat": 0.87, "lon": 99.83, "name": "Lubuk Sikaping"},
    "tanah datar": {"lat": -0.43, "lon": 100.18, "name": "Batusangkar"},
    "limapuluh kota": {"lat": -0.68, "lon": 100.55, "name": "Lubuk Basung"},
    "pesisir selatan": {"lat": -1.70, "lon": 100.80, "name": "Painan"},
    # Riau
    "riau": {"lat": -0.50, "lon": 101.45, "name": "Provinsi Riau"},
    "pekanbaru": {"lat": -0.51, "lon": 101.44, "name": "Pekanbaru"},
    "dumai": {"lat": 1.67, "lon": 101.45, "name": "Dumai"},
    "indragiri hulu": {"lat": -0.40, "lon": 102.30, "name": "Rengat"},
    "indragiri hilir": {"lat": -0.25, "lon": 103.38, "name": "Tembilahan"},
    "kepulauan riau": {"lat": 3.50, "lon": 106.20, "name": "Tanjung Pinang"},
    "bintan": {"lat": 1.30, "lon": 104.55, "name": "Tanjung Uban"},
    "lingga": {"lat": -0.07, "lon": 104.65, "name": "Daik"},
    "rohul": {"lat": 1.00, "lon": 100.55, "name": "Pasir Pengaraian"},
    "rohil": {"lat": 0.92, "lon": 101.42, "name": "Bangkinang"},
    "bengkalis": {"lat": 1.50, "lon": 102.35, "name": "Bengkalis"},
    "siak": {"lat": 1.30, "lon": 102.05, "name": "Siak Sri Indrapura"},
    "kuantan singingi": {"lat": -0.73, "lon": 101.87, "name": "Teluk Kuantan"},
    # Jambi
    "jambi": {"lat": -1.59, "lon": 103.61, "name": "Jambi"},
    "sungai penuh": {"lat": -2.06, "lon": 101.38, "name": "Sungai Penuh"},
    "batanghari": {"lat": -1.75, "lon": 103.05, "name": "Muara Bulian"},
    "bistik": {"lat": -1.90, "lon": 104.62, "name": "Kota Bistik"},
    "kerinci": {"lat": -2.13, "lon": 101.47, "name": "Siulak"},
    "merangin": {"lat": -2.28, "lon": 102.10, "name": "Bangko"},
    "muaro jambi": {"lat": -1.55, "lon": 103.80, "name": "Sengeti"},
    "sarolangun": {"lat": -2.33, "lon": 102.95, "name": "Sarolangun"},
    "tanjung jabung barat": {"lat": -0.27, "lon": 102.30, "name": "Kuala Tungkal"},
    "tanjung jabung timur": {"lat": 0.15, "lon": 103.12, "name": "Kuala Berambo"},
    "tebo": {"lat": -1.47, "lon": 102.20, "name": "Muara Tebo"},
    # Sumatra Selatan
    "palembang": {"lat": -2.99, "lon": 104.76, "name": "Palembang"},
    "lubuklinggau": {"lat": -3.29, "lon": 102.86, "name": "Lubuklinggau"},
    "prabumulih": {"lat": -3.42, "lon": 103.42, "name": "Prabumulih"},
    "pagar alam": {"lat": -4.03, "lon": 103.25, "name": "Pagar Alam"},
    "banyuasin": {"lat": -2.42, "lon": 104.58, "name": "Pangkalan Balai"},
    "muara enim": {"lat": -3.80, "lon": 103.45, "name": "Tanjungenim"},
    "ogan ilir": {"lat": -3.30, "lon": 104.50, "name": "Indralaya"},
    "ogan komering ilir": {"lat": -3.00, "lon": 105.25, "name": "Kayuagung"},
    "ogan komering ulu": {"lat": -4.00, "lon": 103.90, "name": "Martapura"},
    "empat lawang": {"lat": -3.80, "lon": 102.90, "name": "Tebing Tinggi"},
    "lahat": {"lat": -3.79, "lon": 103.53, "name": "Lahat"},
    "musi banyuasin": {"lat": -2.50, "lon": 103.60, "name": "Sekayu"},
    "musi rawas": {"lat": -3.20, "lon": 103.10, "name": "Muaratelang"},
    "musi rawas utara": {"lat": -2.60, "lon": 102.50, "name": "Rupit"},
    "penukal abab lematang ilir": {"lat": -3.30, "lon": 103.50, "name": "Talang Ubi"},
    # Bengkulu
    "bengkulu": {"lat": -3.80, "lon": 102.26, "name": "Bengkulu"},
    "rejang lebong": {"lat": -3.43, "lon": 102.68, "name": "Curup"},
    "kepahiang": {"lat": -3.60, "lon": 102.60, "name": "Kepahiang"},
    "lebong": {"lat": -3.10, "lon": 102.25, "name": "Muara Aman"},
    "kaur": {"lat": -4.45, "lon": 103.42, "name": "Bintuhan"},
    "bengkulu selatan": {"lat": -4.42, "lon": 103.08, "name": "Manna"},
    "bengkulu tengah": {"lat": -3.31, "lon": 102.33, "name": "Karang Tinggi"},
    "bengkulu utara": {"lat": -3.20, "lon": 101.73, "name": "Arga Makmur"},
    "seluma": {"lat": -4.10, "lon": 102.65, "name": "Pasar Muara Bungo"},
    # Lampung
    "lampung": {"lat": -5.45, "lon": 105.26, "name": "Bandar Lampung"},
    "metro": {"lat": -5.12, "lon": 105.32, "name": "Metro"},
    "lampung barat": {"lat": -5.12, "lon": 104.02, "name": "Kalianda"},
    "lampung selatan": {"lat": -5.55, "lon": 105.52, "name": "Kalianda"},
    "lampung tengah": {"lat": -4.80, "lon": 105.27, "name": "Gunung Sugih"},
    "lampung timur": {"lat": -5.10, "lon": 105.70, "name": "Sukadana"},
    "lampung utara": {"lat": -4.80, "lon": 104.75, "name": "Kotabumi"},
    "pesisir barat": {"lat": -5.17, "lon": 104.00, "name": "Krui"},
    "tulang bawang": {"lat": -4.50, "lon": 105.62, "name": "Menggala"},
    "way kanan": {"lat": -4.35, "lon": 104.58, "name": "Blambangan Umpu"},
    "mesuji": {"lat": -4.55, "lon": 105.42, "name": "Mersam"},
    "pesawaran": {"lat": -5.42, "lon": 105.07, "name": "Gedong Tataan"},
    "pringsewu": {"lat": -5.36, "lon": 104.98, "name": "Pringsewu"},
    # Bangka Belitung
    "pangkal pinang": {"lat": -2.13, "lon": 106.12, "name": "Pangkalpinang"},
    "bangka": {"lat": -2.35, "lon": 106.10, "name": "Mentok"},
    "bangka barat": {"lat": -2.00, "lon": 105.42, "name": "Muntok"},
    "bangka selatan": {"lat": -2.85, "lon": 106.18, "name": "Toboali"},
    "bangka tengah": {"lat": -2.55, "lon": 106.00, "name": "Koba"},
    "belitung": {"lat": -3.00, "lon": 107.83, "name": "Tanjung Pandan"},
    "belitung timur": {"lat": -2.92, "lon": 108.15, "name": "Manggar"},
    # ── Jawa ─────────────────────────────────────────────────────────
    "dki jakarta": {"lat": -6.21, "lon": 106.85, "name": "Jakarta"},
    "jakarta": {"lat": -6.21, "lon": 106.85, "name": "Jakarta"},
    "jakarta selatan": {"lat": -6.30, "lon": 106.82, "name": "Jakarta Selatan"},
    "jakarta timur": {"lat": -6.24, "lon": 106.90, "name": "Jakarta Timur"},
    "jakarta barat": {"lat": -6.18, "lon": 106.78, "name": "Jakarta Barat"},
    "jakarta utara": {"lat": -6.13, "lon": 106.87, "name": "Jakarta Utara"},
    "jakarta pusat": {"lat": -6.20, "lon": 106.85, "name": "Jakarta Pusat"},
    "banten": {"lat": -6.10, "lon": 106.15, "name": "Serang"},
    "serang": {"lat": -6.11, "lon": 106.15, "name": "Serang"},
    "cilegon": {"lat": -6.00, "lon": 106.03, "name": "Cilegon"},
    "tangerang": {"lat": -6.17, "lon": 106.63, "name": "Tangerang"},
    "tangerang selatan": {"lat": -6.31, "lon": 106.71, "name": "Tangerang Selatan"},
    "pandeglang": {"lat": -6.32, "lon": 106.12, "name": "Pandeglang"},
    "lebak": {"lat": -6.57, "lon": 106.23, "name": "Rangkasbitung"},
    # Jawa Barat
    "jawa barat": {"lat": -6.94, "lon": 107.61, "name": "Jawa Barat"},
    "bandung": {"lat": -6.92, "lon": 107.61, "name": "Bandung"},
    "bekasi": {"lat": -6.24, "lon": 106.99, "name": "Bekasi"},
    "depok": {"lat": -6.40, "lon": 106.84, "name": "Depok"},
    "bogor": {"lat": -6.59, "lon": 106.79, "name": "Bogor"},
    "cirebon": {"lat": -6.72, "lon": 108.55, "name": "Cirebon"},
    "medan satria": {"lat": -6.16, "lon": 106.88, "name": "Cimahi"},
    "probolinggo": {"lat": -7.94, "lon": 110.12, "name": "Probolinggo"},
    "cimahi": {"lat": -6.87, "lon": 107.57, "name": "Cimahi"},
    "tasikmalaya": {"lat": -7.34, "lon": 108.20, "name": "Tasikmalaya"},
    "banjar": {"lat": -7.37, "lon": 108.57, "name": "Banjar"},
    "garut": {"lat": -7.21, "lon": 107.90, "name": "Garut"},
    "cianjur": {"lat": -6.82, "lon": 107.39, "name": "Cianjur"},
    "sukabumi": {"lat": -6.92, "lon": 106.93, "name": "Sukabumi"},
    "sumedang": {"lat": -6.86, "lon": 107.92, "name": "Sumedang"},
    "subang": {"lat": -6.57, "lon": 107.80, "name": "Subang"},
    "kuningan": {"lat": -6.97, "lon": 108.48, "name": "Kuningan"},
    "majalengka": {"lat": -6.84, "lon": 108.23, "name": "Majalengka"},
    "indramayu": {"lat": -6.35, "lon": 108.32, "name": "Indramayu"},
    "karawang": {"lat": -6.32, "lon": 107.33, "name": "Karawang"},
    "purwakarta": {"lat": -6.56, "lon": 107.45, "name": "Purwakarta"},
    "bandung barat": {"lat": -6.87, "lon": 107.47, "name": "Padalarang"},
    # Jawa Tengah
    "jawa tengah": {"lat": -7.15, "lon": 110.40, "name": "Jawa Tengah"},
    "semarang": {"lat": -6.97, "lon": 110.42, "name": "Semarang"},
    "salatiga": {"lat": -7.33, "lon": 110.50, "name": "Salatiga"},
    "solo": {"lat": -7.58, "lon": 110.82, "name": "Surakarta (Solo)"},
    "surakarta": {"lat": -7.58, "lon": 110.82, "name": "Surakarta (Solo)"},
    "maguwoharjo": {"lat": -7.80, "lon": 110.40, "name": "Sleman"},
    "magelang": {"lat": -7.48, "lon": 110.22, "name": "Magelang"},
    "purwokerto": {"lat": -7.43, "lon": 109.23, "name": "Purwokerto"},
    "tegal": {"lat": -6.88, "lon": 109.12, "name": "Tegal"},
    "pekalongan": {"lat": -6.89, "lon": 109.67, "name": "Pekalongan"},
    "kudus": {"lat": -6.80, "lon": 110.62, "name": "Kudus"},
    "jepara": {"lat": -6.58, "lon": 110.67, "name": "Jepara"},
    "temanggung": {"lat": -7.32, "lon": 110.17, "name": "Temanggung"},
    "kendal": {"lat": -7.03, "lon": 110.20, "name": "Kendal"},
    "demak": {"lat": -6.93, "lon": 110.63, "name": "Demak"},
    "pemalang": {"lat": -6.88, "lon": 109.48, "name": "Pemalang"},
    "purbalingga": {"lat": -7.38, "lon": 109.36, "name": "Purbalingga"},
    "banjarnegara": {"lat": -7.37, "lon": 109.69, "name": "Banjarnegara"},
    "pati": {"lat": -6.75, "lon": 111.05, "name": "Pati"},
    "kebumen": {"lat": -7.70, "lon": 109.65, "name": "Kebumen"},
    "purworejo": {"lat": -7.72, "lon": 110.02, "name": "Purworejo"},
    "wonogiri": {"lat": -7.82, "lon": 110.92, "name": "Wonogiri"},
    "klaten": {"lat": -7.61, "lon": 110.60, "name": "Klaten"},
    "batang": {"lat": -6.98, "lon": 110.32, "name": "Batang"},
    "wonosobo": {"lat": -7.37, "lon": 109.90, "name": "Wonosobo"},
    "brebes": {"lat": -6.87, "lon": 109.03, "name": "Brebes"},
    "blora": {"lat": -6.95, "lon": 111.42, "name": "Blora"},
    "grobogan": {"lat": -7.03, "lon": 110.95, "name": "Purwodadi"},
    # DI Yogyakarta
    "yogyakarta": {"lat": -7.80, "lon": 110.36, "name": "Yogyakarta"},
    "sleman": {"lat": -7.72, "lon": 110.33, "name": "Sleman"},
    "gunung kidul": {"lat": -7.95, "lon": 110.62, "name": "Wonosari"},
    "bantul": {"lat": -7.88, "lon": 110.32, "name": "Bantul"},
    "kulon progo": {"lat": -7.82, "lon": 110.17, "name": "Wates"},
    # Jawa Timur
    "jawa timur": {"lat": -7.54, "lon": 112.88, "name": "Jawa Timur"},
    "surabaya": {"lat": -7.26, "lon": 112.75, "name": "Surabaya"},
    "malang": {"lat": -7.98, "lon": 112.63, "name": "Malang"},
    "kediri": {"lat": -7.82, "lon": 112.02, "name": "Kediri"},
    "blitar": {"lat": -8.09, "lon": 112.17, "name": "Blitar"},
    "mojokerto": {"lat": -7.47, "lon": 112.43, "name": "Mojokerto"},
    "pasuruan": {"lat": -7.63, "lon": 112.91, "name": "Pasuruan"},
    "probolinggo": {"lat": -7.75, "lon": 113.22, "name": "Probolinggo"},
    "madiun": {"lat": -7.62, "lon": 111.53, "name": "Madiun"},
    "batu": {"lat": -7.87, "lon": 112.53, "name": "Batu"},
    "tuban": {"lat": -6.90, "lon": 111.87, "name": "Tuban"},
    "madura": {"lat": -7.15, "lon": 113.90, "name": "Bangkalan"},
    "sumenep": {"lat": -7.02, "lon": 113.88, "name": "Sumenep"},
    "sampang": {"lat": -7.18, "lon": 113.25, "name": "Sampang"},
    "pamekasan": {"lat": -7.16, "lon": 113.47, "name": "Pamekasan"},
    # ── Kalimantan ───────────────────────────────────────────────────
    "kalimantan": {"lat": -1.50, "lon": 113.00, "name": "Pulau Kalimantan"},
    "pontianak": {"lat": -0.03, "lon": 109.33, "name": "Pontianak"},
    "palangkaraya": {"lat": -2.21, "lon": 113.92, "name": "Palangkaraya"},
    "bontang": {"lat": 0.13, "lon": 117.50, "name": "Bontang"},
    "samarinda": {"lat": -0.50, "lon": 117.15, "name": "Samarinda"},
    "balikpapan": {"lat": -1.27, "lon": 116.83, "name": "Balikpapan"},
    "tanjung selor": {"lat": 2.84, "lon": 117.32, "name": "Tanjung Selor"},
    "banjarbaru": {"lat": -3.44, "lon": 114.83, "name": "Banjarbaru"},
    "banjarmasin": {"lat": -3.32, "lon": 114.59, "name": "Banjarmasin"},
    "singkawang": {"lat": 0.90, "lon": 108.98, "name": "Singkawang"},
    "sintang": {"lat": 0.03, "lon": 111.50, "name": "Sintang"},
    "ketapang": {"lat": -1.83, "lon": 109.97, "name": "Ketapang"},
    "mempawah": {"lat": 0.22, "lon": 109.20, "name": "Mempawah"},
    "sambas": {"lat": 1.42, "lon": 109.30, "name": "Sambas"},
    "bengkayang": {"lat": 1.18, "lon": 109.60, "name": "Bengkayang"},
    "landak": {"lat": 0.82, "lon": 109.77, "name": "Ngabang"},
    "sekadau": {"lat": 0.93, "lon": 110.88, "name": "Sekadau"},
    "kapuas hulu": {"lat": 0.85, "lon": 114.00, "name": "Putussibau"},
    "katingan": {"lat": -1.83, "lon": 113.38, "name": "Kasongan"},
    "gunung mas": {"lat": -1.55, "lon": 113.30, "name": "Kuala Kurun"},
    "kapuas": {"lat": -2.92, "lon": 114.40, "name": "Kuala Kapuas"},
    "barito selatan": {"lat": -2.22, "lon": 115.17, "name": "Buntok"},
    "barito utara": {"lat": -1.83, "lon": 116.03, "name": "Muara Teweh"},
    "barito timur": {"lat": -1.73, "lon": 115.78, "name": "Tamiang Layang"},
    "barito Kuala": {"lat": -2.72, "lon": 115.08, "name": "Marabahan"},
    "hulu sungai tengah": {"lat": -2.65, "lon": 115.35, "name": "Barabai"},
    "hulu sungai utara": {"lat": -2.55, "lon": 115.78, "name": "Amuntai"},
    "hulu sungai selatan": {"lat": -2.50, "lon": 115.17, "name": "Kandangan"},
    "tabalong": {"lat": -2.13, "lon": 115.43, "name": "Tanjung"},
    "tanah bumi": {"lat": -3.23, "lon": 115.63, "name": "Tanjung"},
    "tanah laut": {"lat": -3.80, "lon": 115.55, "name": "Pelaihari"},
    "kotabaru": {"lat": -3.30, "lon": 116.22, "name": "Kotabaru"},
    # ── Sulawesi ─────────────────────────────────────────────────────
    "sulawesi": {"lat": -2.50, "lon": 121.00, "name": "Pulau Sulawesi"},
    "sulawesi utara": {"lat": 1.50, "lon": 125.00, "name": "Sulawesi Utara"},
    "manado": {"lat": 1.49, "lon": 124.84, "name": "Manado"},
    "minahasa": {"lat": 1.35, "lon": 124.90, "name": "Tondano"},
    "bitung": {"lat": 1.44, "lon": 125.12, "name": "Bitung"},
    "tomohon": {"lat": 1.31, "lon": 124.84, "name": "Tomohon"},
    "kotamobagu": {"lat": 0.73, "lon": 124.30, "name": "Kotamobagu"},
    "bolaang mongondow": {"lat": 0.95, "lon": 124.55, "name": "Kuala Simpang"},
    "bolaang mongondow selatan": {"lat": 0.65, "lon": 123.92, "name": "Bolang Itang"},
    "bolaang mongondow timur": {"lat": 1.15, "lon": 124.75, "name": "Tutuyan"},
    "bolaang mongondow utara": {"lat": 1.38, "lon": 125.00, "name": "Lolayan"},
    "kepulauan sahu": {"lat": 1.40, "lon": 125.20, "name": "Tahuna"},
    "minahasa selatan": {"lat": 1.20, "lon": 124.55, "name": "Amurang"},
    "minahasa tenggara": {"lat": 1.05, "lon": 124.45, "name": "Ratahan"},
    "minahasa utara": {"lat": 1.70, "lon": 124.75, "name": "Airmadidi"},
    "kepulauan siau tagulandang biaro": {"lat": 2.40, "lon": 125.50, "name": "Ondong"},
    # Sulawesi Tengah
    "sulawesi tengah": {"lat": -0.90, "lon": 119.87, "name": "Sulawesi Tengah"},
    "palu": {"lat": -0.89, "lon": 119.87, "name": "Palu"},
    "poso": {"lat": -1.39, "lon": 120.75, "name": "Poso"},
    "donga": {"lat": -0.62, "lon": 121.40, "name": "Kendari"},
    "sigi": {"lat": -1.03, "lon": 119.87, "name": "Sigi Biromaru"},
    "banawa": {"lat": -0.63, "lon": 119.47, "name": "Banawa"},
    "parigi moutong": {"lat": 0.10, "lon": 120.17, "name": "Parigi"},
    "tojo una una": {"lat": 1.18, "lon": 121.57, "name": "Ampana"},
    "banggai kepulauan": {"lat": -1.50, "lon": 123.17, "name": "Banggai"},
    "banggai": {"lat": -1.20, "lon": 122.58, "name": "Luwuk"},
    "morowali": {"lat": -2.52, "lon": 121.92, "name": "Kolonodale"},
    "morowali utara": {"lat": -2.10, "lon": 121.32, "name": "Bungku"},
    "toli toli": {"lat": 1.03, "lon": 120.57, "name": "Toli Toli"},
    # Sulawesi Selatan
    "sulawesi selatan": {"lat": -3.32, "lon": 119.42, "name": "Sulawesi Selatan"},
    "makassar": {"lat": -5.15, "lon": 119.43, "name": "Makassar"},
    "pare pare": {"lat": -4.02, "lon": 119.62, "name": "Parepare"},
    "palopo": {"lat": -2.99, "lon": 120.20, "name": "Palopo"},
    "enrekang": {"lat": -4.56, "lon": 119.57, "name": "Enrekang"},
    "sinjai": {"lat": -5.12, "lon": 120.17, "name": "Sinjai"},
    "bulukumba": {"lat": -5.40, "lon": 120.23, "name": "Bulukumba"},
    "bantaeng": {"lat": -5.52, "lon": 119.98, "name": "Bantaeng"},
    "jenoeponto": {"lat": -5.70, "lon": 119.90, "name": "Jeneponto"},
    "takalar": {"lat": -5.33, "lon": 119.47, "name": "Takalar"},
    "gowa": {"lat": -5.30, "lon": 119.73, "name": "Sungguminasa"},
    "maros": {"lat": -5.03, "lon": 119.58, "name": "Maros"},
    "pangkajene kepulauan": {"lat": -4.83, "lon": 119.57, "name": "Pangkajene"},
    "pinrang": {"lat": -3.78, "lon": 119.65, "name": "Pinrang"},
    "sidenreng rappang": {"lat": -4.13, "lon": 119.93, "name": "S. Rappang"},
    "barru": {"lat": -4.43, "lon": 119.63, "name": "Barru"},
    "bone": {"lat": -4.02, "lon": 120.30, "name": "Watampone"},
    "soppeng": {"lat": -4.35, "lon": 119.88, "name": "Watansoppeng"},
    "wajo": {"lat": -4.07, "lon": 120.13, "name": "Sengkang"},
    "luwu": {"lat": -3.22, "lon": 120.18, "name": "Masamba"},
    "luwu timur": {"lat": -2.93, "lon": 121.13, "name": "Andolo"},
    "luwu utara": {"lat": -3.00, "lon": 120.23, "name": "Malili"},
    # Sulawesi Tenggara
    "sulawesi tenggara": {"lat": -4.00, "lon": 122.20, "name": "Sulawesi Tenggara"},
    "kendari": {"lat": -3.97, "lon": 122.60, "name": "Kendari"},
    "bau bau": {"lat": -5.47, "lon": 120.35, "name": "Baubau"},
    "konawe": {"lat": -3.70, "lon": 122.17, "name": "Unaaha"},
    "kolaka": {"lat": -4.12, "lon": 121.57, "name": "Kolaka"},
    "wakatobi": {"lat": -5.25, "lon": 123.42, "name": "Wangiwangi"},
    "muna": {"lat": -4.85, "lon": 122.70, "name": "Raha"},
    "buton": {"lat": -5.50, "lon": 122.58, "name": "Pasarwajo"},
    # Sulawesi Barat
    "sulawesi barat": {"lat": -2.68, "lon": 118.92, "name": "Sulawesi Barat"},
    "mamuju": {"lat": -2.68, "lon": 118.92, "name": "Mamuju"},
    "majene": {"lat": -3.53, "lon": 118.97, "name": "Majene"},
    "mamuju tengah": {"lat": -1.47, "lon": 118.67, "name": "Tobadak"},
    "mamuju utara": {"lat": 1.18, "lon": 119.63, "name": "Pasangkayu"},
    "polewali mandar": {"lat": -3.43, "lon": 119.32, "name": "Polewali"},
    # Gorontalo
    "gorontalo": {"lat": 0.54, "lon": 123.06, "name": "Gorontalo"},
    "boalemo": {"lat": 0.83, "lon": 122.12, "name": "Lahomi"},
    "gorontalo utara": {"lat": 1.27, "lon": 122.62, "name": "Atinggola"},
    "gorontalo selatan": {"lat": 0.55, "lon": 122.63, "name": "Dulupi"},
    "pohuwato": {"lat": 0.73, "lon": 121.42, "name": "Popayato"},
    # ── Nusa Tenggara & Bali ──────────────────────────────────────────
    "bali": {"lat": -8.50, "lon": 115.10, "name": "Bali"},
    "denpasar": {"lat": -8.65, "lon": 115.22, "name": "Denpasar"},
    "gianyar": {"lat": -8.53, "lon": 115.55, "name": "Gianyar"},
    "badung": {"lat": -8.60, "lon": 115.18, "name": "Mangupura"},
    "buleleng": {"lat": -8.12, "lon": 115.08, "name": "Singaraja"},
    "tabanan": {"lat": -8.55, "lon": 115.08, "name": "Tabanan"},
    "klungkung": {"lat": -8.53, "lon": 115.55, "name": "Semarapura"},
    "jembrana": {"lat": -8.23, "lon": 114.65, "name": "Negara"},
    "karang asem": {"lat": -8.45, "lon": 115.63, "name": "Karangasem"},
    "bangli": {"lat": -8.45, "lon": 115.58, "name": "Bangli"},
    # NTB
    "ntb": {"lat": -8.65, "lon": 117.22, "name": "Nusa Tenggara Barat"},
    "mataram": {"lat": -8.58, "lon": 116.12, "name": "Mataram"},
    "bima": {"lat": -8.47, "lon": 118.72, "name": "Bima"},
    "dompu": {"lat": -8.53, "lon": 118.47, "name": "Dompu"},
    "lombok barat": {"lat": -8.65, "lon": 116.07, "name": "Gerentang"},
    "lombok tengah": {"lat": -8.65, "lon": 116.32, "name": "Praya"},
    "lombok timur": {"lat": -8.55, "lon": 116.57, "name": "Selong"},
    "lombok utara": {"lat": -8.33, "lon": 116.45, "name": "Tanjung"},
    "sumbawa": {"lat": -8.47, "lon": 117.40, "name": "Sumbawa Besar"},
    "sumbawa barat": {"lat": -8.65, "lon": 116.98, "name": "Taliwang"},
    # NTT
    "ntt": {"lat": -10.17, "lon": 123.60, "name": "Nusa Tenggara Timur"},
    "kupang": {"lat": -10.17, "lon": 123.60, "name": "Kupang"},
    "ende": {"lat": -8.83, "lon": 121.67, "name": "Ende"},
    "maumere": {"lat": -8.62, "lon": 122.23, "name": "Sikka"},
    "labuan bajo": {"lat": -8.48, "lon": 119.88, "name": "Labuan Bajo"},
    "ruteng": {"lat": -8.62, "lon": 120.47, "name": "Ruteng"},
    "kefamenanu": {"lat": -9.45, "lon": 124.95, "name": "Kefamenanu"},
    "atambua": {"lat": -9.08, "lon": 124.90, "name": "Atambua"},
    "larantuka": {"lat": -8.33, "lon": 122.98, "name": "Larantuka"},
    "waingapu": {"lat": -9.63, "lon": 120.27, "name": "Waingapu"},
    "kota baru": {"lat": -10.07, "lon": 122.92, "name": "Kota Baru"},
    # ── Kalimantan (fire-prone peatland & forest regions) ────────────
    "riau peatland": {"lat": -0.50, "lon": 101.50, "name": "Riau (Gambut Riau)"},
    "kabupaten indragiri hulu": {"lat": -0.45, "lon": 101.55, "name": "Kab. Indragiri Hulu"},
    "kabupaten kuantan singingi": {"lat": -0.70, "lon": 101.90, "name": "Kab. Kuantan Singingi"},
    "kabupaten siak": {"lat": 1.20, "lon": 102.20, "name": "Kab. Siak"},
    "kabupaten kampar": {"lat": 0.28, "lon": 101.18, "name": "Kab. Kampar"},
    "kabupaten rohil": {"lat": 0.90, "lon": 101.50, "name": "Kab. Rokan Hulu"},
    "kabupaten rohul": {"lat": 1.08, "lon": 100.65, "name": "Kab. Rokan Hilir"},
    "kabupaten Bengkalis": {"lat": 1.50, "lon": 102.10, "name": "Kab. Bengkalis"},
    "central kalimantan peatland": {"lat": -2.21, "lon": 113.92, "name": "Kalimantan Tengah (Gambut)"},
    "south kalimantan peatland": {"lat": -3.32, "lon": 114.59, "name": "Kalimantan Selatan (Gambut)"},
    "kabupaten hulu sungai tengah": {"lat": -2.65, "lon": 115.35, "name": "Kab. Hulu Sungai Tengah"},
    "kabupaten hulu sungai utara": {"lat": -2.55, "lon": 115.78, "name": "Kab. Hulu Sungai Utara"},
    "kabupaten barito selatan": {"lat": -2.22, "lon": 115.17, "name": "Kab. Barito Selatan"},
    "kabupaten barito utara": {"lat": -1.83, "lon": 116.03, "name": "Kab. Barito Utara"},
    "kabupaten gunung mas": {"lat": -1.60, "lon": 113.50, "name": "Kab. Gunung Mas"},
    "kabupaten katingan": {"lat": -2.00, "lon": 113.20, "name": "Kab. Katingan"},
    "kabupaten kubu raya": {"lat": 0.22, "lon": 109.20, "name": "Kab. Kubu Raya"},
    "kabupaten landak": {"lat": 0.82, "lon": 109.77, "name": "Kab. Landak"},
    # ── Papua ────────────────────────────────────────────────────────
    "papua": {"lat": -5.20, "lon": 140.70, "name": "Papua"},
    "jaya wijaya": {"lat": -4.10, "lon": 138.95, "name": "Jayapura"},
    "jayapura": {"lat": -2.53, "lon": 140.72, "name": "Jayapura"},
    "merauke": {"lat": -8.50, "lon": 140.38, "name": "Merauke"},
    "biak numfor": {"lat": -1.18, "lon": 136.07, "name": "Biak"},
    "sorong": {"lat": -0.88, "lon": 131.25, "name": "Sorong"},
    "manokwari": {"lat": -0.86, "lon": 134.07, "name": "Manokwari"},
    "nabire": {"lat": -3.35, "lon": 135.50, "name": "Nabire"},
    "timika": {"lat": -4.55, "lon": 136.87, "name": "Timika"},
    "weriagar": {"lat": -1.83, "lon": 133.02, "name": "Weriagar"},
    "tambrauw": {"lat": -1.08, "lon": 132.47, "name": "Ayamaru"},
    "kaimana": {"lat": -3.65, "lon": 133.75, "name": "Kaimana"},
    "teluk bintuni": {"lat": -2.40, "lon": 133.42, "name": "Bintuni"},
    "teluk wondama": {"lat": -2.70, "lon": 134.50, "name": "Rasiei"},
    "yapen waropen": {"lat": -2.13, "lon": 136.17, "name": "Serui"},
    "sarmi": {"lat": -1.85, "lon": 138.68, "name": "Sarmi"},
    "keerom": {"lat": -3.38, "lon": 140.70, "name": "Waris"},
    "waropen": {"lat": -2.72, "lon": 136.53, "name": "Botawa"},
    "supiori": {"lat": -0.78, "lon": 135.65, "name": "Sorendiweri"},
    "mamberamo": {"lat": -3.20, "lon": 138.80, "name": "Kobakre"},
    "nakanai": {"lat": -1.68, "lon": 134.37, "name": "Sausapor"},
    "boven digoel": {"lat": -6.17, "lon": 140.80, "name": "Tanahmerah"},
    "mappi": {"lat": -6.40, "lon": 139.42, "name": "Oktem"},
    "asmat": {"lat": -5.18, "lon": 138.25, "name": "Agats"},
    "yahukimo": {"lat": -4.90, "lon": 139.97, "name": "Dekai"},
    "pegunungan bintang": {"lat": -4.52, "lon": 140.75, "name": "Oksibil"},
    "tolikara": {"lat": -3.62, "lon": 138.68, "name": "Karubaga"},
    "sentral papua": {"lat": -3.37, "lon": 138.35, "name": "Sentral Papua"},
    "nabire": {"lat": -3.35, "lon": 135.50, "name": "Nabire"},
    "doberai": {"lat": -4.13, "lon": 136.88, "name": "Doberai"},
    "pegaf": {"lat": -3.98, "lon": 136.57, "name": "Pegaf"},
    "puncak": {"lat": -4.12, "lon": 137.25, "name": "Ilaga"},
    "puncak jaya": {"lat": -4.08, "lon": 137.17, "name": "Mulia"},
    "nduga": {"lat": -4.52, "lon": 138.86, "name": "Kenyam"},
    "highland papua": {"lat": -4.12, "lon": 139.13, "name": "Wamena"},
    "wamena": {"lat": -4.10, "lon": 138.93, "name": "Wamena"},
    "lanoepo": {"lat": -4.30, "lon": 137.72, "name": "Lanoepo"},
    "abiageh": {"lat": -4.48, "lon": 138.87, "name": "Abiageh"},
    # ── Maluku & Maluku Utara ─────────────────────────────────────────
    "maluku": {"lat": -3.75, "lon": 128.20, "name": "Maluku"},
    "ambon": {"lat": -3.70, "lon": 128.17, "name": "Ambon"},
    "tual": {"lat": -4.97, "lon": 131.72, "name": "Tual"},
    "tulehu": {"lat": -3.65, "lon": 128.22, "name": "Tulehu"},
    "masohi": {"lat": -3.27, "lon": 128.72, "name": "Masohi"},
    "maluku tengah": {"lat": -3.18, "lon": 128.90, "name": "Maluku Tengah"},
    "seram bagian selatan": {"lat": -3.52, "lon": 128.93, "name": "Saparua"},
    "buru selatan": {"lat": -3.60, "lon": 126.62, "name": "Namlea"},
    "buru": {"lat": -3.30, "lon": 126.60, "name": "Namlea"},
    # ── Local helper entries (kept from original) ────────────────────
}


def geocode_location(location_name: str) -> Dict[str, Any]:
    """
    Geocode location name to coordinates
    Uses local database first, then falls back to Nominatim API
    """

    if not location_name:
        return None

    location_lower = location_name.lower().strip()

    # Check local database first
    for key, value in INDONESIA_LOCATIONS.items():
        if key in location_lower or location_lower in key:
            return {
                "lat": value["lat"],
                "lon": value["lon"],
                "name": value["name"],
                "source": "local",
            }

    # Try Nominatim API (OpenStreetMap) for other locations
    try:
        url = "https://nominatim.openstreetmap.org/search"
        params = {"q": f"{location_name}, Indonesia", "format": "json", "limit": 1}
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()

        results = response.json()
        if results:
            result = results[0]
            return {
                "lat": float(result["lat"]),
                "lon": float(result["lon"]),
                "name": result.get("display_name", location_name),
                "source": "nominatim",
            }
    except Exception as e:
        logger.error(f"Geocoding error: {e}")
        # Continue without location name - will use defaults

    return None


def _get_float(key: str, default: float) -> float:
    """Get a float value from session state, falling back to default if not numeric."""
    v = st.session_state.get(key, default)
    if isinstance(v, (int, float)):
        return float(v)
    return float(default)

def _get_int(key: str, default: int) -> int:
    """Get an int value from session state, falling back to default if not numeric."""
    v = st.session_state.get(key, default)
    if isinstance(v, (int, float)):
        return int(v)
    return int(default)


def render_sidebar() -> Dict[str, Any]:
    """
    Render sidebar input components.
    Returns dictionary with all input parameters.
    """
    
    input_data = {}
    
    # ── Location search / selection ───────────────────────────────────
    st.markdown("### 🔍 Lokasi")
    
    # Build display names for all locations (sorted, popular first)
    _location_display_names = ["-- Pilih Lokasi --"]
    _location_name_map = {}
    _popular = ["jakarta", "surabaya", "medan", "bandung", "yogyakarta",
                "riau", "kabupaten indragiri hulu", "pekanbaru"]
    for name in _popular:
        if name in INDONESIA_LOCATIONS:
            val = INDONESIA_LOCATIONS[name]
            display = val["name"]
            _location_display_names.append(display)
            _location_name_map[display] = name
    for key in INDONESIA_LOCATIONS:
        if key not in _popular:
            val = INDONESIA_LOCATIONS[key]
            display = val["name"]
            _location_display_names.append(display)
            _location_name_map[display] = key
    
    current_loc = st.session_state.get(
        "selected_location", {"lat": -1.1747, "lon": 100.4012, "name": "Indonesia (Default)"}
    )
    current_name = current_loc.get("name", "Indonesia (Default)")
    selected_display = current_name if current_name in _location_display_names else "-- Pilih Lokasi --"
    default_idx = _location_display_names.index(selected_display) if selected_display in _location_display_names else 0
    
    chosen_display = st.selectbox(
        "Pilih Lokasi",
        options=_location_display_names,
        index=default_idx,
        help="Cari dan pilih lokasi untuk prediksi",
    )
    
    if chosen_display != "-- Pilih Lokasi --":
        loc_key = _location_name_map[chosen_display]
        loc = INDONESIA_LOCATIONS[loc_key]
        st.session_state.selected_location = {
            "lat": loc["lat"],
            "lon": loc["lon"],
            "name": loc["name"],
        }
    
    selected_loc = st.session_state.get(
        "selected_location", {"lat": -1.1747, "lon": 100.4012, "name": "Indonesia (Default)"}
    )
    input_data["latitude"] = selected_loc.get("lat", -1.1747)
    input_data["longitude"] = selected_loc.get("lon", 100.4012)
    input_data["location_name"] = selected_loc.get("name", "lokasi ini")
    
    # ── Custom location input ─────────────────────────────────────────
    st.caption("Atau masukkan koordinat secara manual:")
    col_lat, col_lon = st.columns(2)
    with col_lat:
        custom_lat = st.number_input("Latitude", value=float(input_data["latitude"]), format="%.4f", key="custom_lat")
    with col_lon:
        custom_lon = st.number_input("Longitude", value=float(input_data["longitude"]), format="%.4f", key="custom_lon")
    
    if st.button("📍 Terapkan Koordinat", use_container_width=True, key="apply_coords"):
        st.session_state.selected_location = {
            "lat": custom_lat,
            "lon": custom_lon,
            "name": f"Custom: {custom_lat:.4f}°, {custom_lon:.4f}°",
        }
        st.rerun()
    
    # Re-read location after possible update
    selected_loc = st.session_state.get(
        "selected_location", {"lat": -1.1747, "lon": 100.4012, "name": "Indonesia (Default)"}
    )
    input_data["latitude"] = selected_loc.get("lat", -1.1747)
    input_data["longitude"] = selected_loc.get("lon", 100.4012)
    input_data["location_name"] = selected_loc.get("name", "lokasi ini")
    
    # ── Location display ─────────────────────────────────────────────
    st.caption(f"📍 Prediksi untuk: {input_data['location_name']} ({input_data['latitude']:.4f}, {input_data['longitude']:.4f})")
    
    st.markdown("---")
    
    # ── Preset Scenarios ───────────────────────────────────────────────
    st.markdown("### 🎯 Preset Skenario")
    col_p1, col_p2 = st.columns(2)
    col_p3, col_p4 = st.columns(2)
    
    with col_p1:
        if st.button("🔥 Kekeringan", use_container_width=True, help="Suhu tinggi, kelembaban rendah, tanpa hujan"):
            st.session_state.preset_applied = "drought"
            st.rerun()
    
    with col_p2:
        if st.button("🌧️ Badai", use_container_width=True, help="Hujan tinggi, kelembaban tinggi, angin kencang"):
            st.session_state.preset_applied = "storm"
            st.rerun()
    
    with col_p3:
        if st.button("💨 Angin Kencang", use_container_width=True, help="Angin sangat kencang, suhu sedang"):
            st.session_state.preset_applied = "windy"
            st.rerun()
    
    with col_p4:
        if st.button("🌿 Normal", use_container_width=True, help="Kondisi cuaca standar"):
            st.session_state.preset_applied = "normal"
            st.rerun()
    
    # Apply preset if selected
    if "preset_applied" in st.session_state:
        preset = st.session_state.preset_applied
        presets = {
            "drought": {
                "temperature": 42.0, "humidity": 20, "wind_speed": 8.0,
                "wind_direction": 180, "rainfall": 0.0, "fuel_moisture": 15,
            },
            "storm": {
                "temperature": 24.0, "humidity": 95, "wind_speed": 18.0,
                "wind_direction": 270, "rainfall": 150.0, "fuel_moisture": 75,
            },
            "windy": {
                "temperature": 30.0, "humidity": 50, "wind_speed": 25.0,
                "wind_direction": 90, "rainfall": 0.0, "fuel_moisture": 40,
            },
            "normal": {
                "temperature": 32.0, "humidity": 65, "wind_speed": 5.0,
                "wind_direction": 45, "rainfall": 5.0, "fuel_moisture": 45,
            },
        }
        if preset in presets:
            for key, value in presets[preset].items():
                st.session_state[f"preset_{key}"] = value
        del st.session_state.preset_applied
        st.success("✅ Preset diterapkan!")
    
    st.markdown("---")
    
    # ── Auto-fetch weather data ───────────────────────────────────────
    lat = input_data["latitude"]
    lon = input_data["longitude"]
    if lat is not None and lon is not None:
        loc_key = (round(lat, 4), round(lon, 4))
        last_loc = st.session_state.get("last_fetched_location")
        if loc_key != last_loc:
            location_name = input_data["location_name"]
            with st.spinner(f"Mengambil data cuaca untuk {location_name}..."):
                try:
                    weather = get_weather_data(lat, lon)
                    input_data["temperature"] = weather.get("temperature", 32.0)
                    input_data["humidity"] = weather.get("humidity", 50)
                    input_data["wind_speed"] = weather.get("wind_speed", 5.0)
                    input_data["wind_direction"] = weather.get("wind_direction", 0)
                    input_data["rainfall"] = weather.get("rainfall", 0.0)
                    st.session_state.preset_temperature = float(input_data["temperature"])
                    st.session_state.preset_humidity = int(input_data["humidity"])
                    st.session_state.preset_wind_speed = float(input_data["wind_speed"])
                    st.session_state.preset_wind_direction = int(input_data["wind_direction"])
                    st.session_state.preset_rainfall = float(input_data["rainfall"])
                    st.session_state.last_fetched_location = loc_key
                    st.success(f"✅ Data cuaca diambil dari {weather.get('source', 'API')}")
                except Exception as e:
                    st.warning(f"⚠️ Gagal mengambil data cuaca: {e}. Menggunakan nilai default.")
    
    # ── Auto-fetch GEE satellite data ──────────────────────────────────
    lat_g = input_data["latitude"]
    lon_g = input_data["longitude"]
    geo_key = (round(lat_g, 4), round(lon_g, 4))
    last_geo = st.session_state.get("last_fetched_gee")
    if geo_key != last_geo:
        location_name = input_data["location_name"]
        with st.spinner(f"Mengambil data satelit & elevasi untuk {location_name}..."):
            try:
                gee_data = get_location_data(lat_g, lon_g)
                input_data["elevation"] = gee_data.get("elevation", 100.0)
                st.session_state.preset_elevation = input_data["elevation"]
                for band in ["B2", "B3", "B4", "B8", "B11", "B12"]:
                    val = gee_data.get(band, 0.0)
                    input_data[band] = val
                    st.session_state[f"preset_{band}"] = val
                lc_code = gee_data.get("land_cover_code", 0)
                input_data["land_cover"] = lc_code
                st.session_state.preset_land_cover = lc_code
                if not st.session_state.get("ndvi_manually_set", False):
                    b8 = gee_data.get("B8", 0.0)
                    b4 = gee_data.get("B4", 0.0)
                    input_data["ndvi"] = (b8 - b4) / (b8 + b4 + 1e-8)
                    st.session_state.preset_ndvi = float(input_data["ndvi"])
                st.session_state.last_fetched_gee = geo_key
                st.success("✅ Data satelit & elevasi diambil (Google Earth Engine)")
            except Exception as e:
                st.warning(f"⚠️ GEE gagal diambil: {e}. Menggunakan nilai default.")
                input_data.update({
                    "elevation": 100.0, "B2": 0.15, "B3": 0.25, "B4": 0.20,
                    "B8": 0.45, "B11": 0.30, "B12": 0.25, "land_cover": 10,
                })
    else:
        # Reuse cached values
        input_data["elevation"] = st.session_state.get("preset_elevation", 100.0)
        for band in ["B2", "B3", "B4", "B8", "B11", "B12"]:
            input_data[band] = st.session_state.get(f"preset_{band}", 0.0)
        input_data["land_cover"] = st.session_state.get("preset_land_cover", 0)
        if "preset_ndvi" in st.session_state:
            input_data["ndvi"] = st.session_state.preset_ndvi
    
    st.markdown("---")
    
    # ── Weather Conditions ────────────────────────────────────────────
    with st.expander("🌤️ Kondisi Cuaca", expanded=True):
        col_temp, col_humidity = st.columns(2)
        with col_temp:
            temperature = st.slider(
                "Suhu (°C)",
                min_value=15.0, max_value=50.0,
                value=_get_float("preset_temperature", 32.0),
                step=0.5, help="Suhu udara saat ini",
            )
            input_data["temperature"] = temperature
        
        with col_humidity:
            humidity = st.slider(
                "Kelembaban (%)",
                min_value=5, max_value=100,
                value=_get_int("preset_humidity", 45),
                step=1, help="Kelembaban udara relatif",
            )
            input_data["humidity"] = humidity
        
        col_ws, col_wd = st.columns(2)
        with col_ws:
            wind_speed = st.slider(
                "Kecepatan Angin (m/s)",
                min_value=0.0, max_value=30.0,
                value=_get_float("preset_wind_speed", 5.0),
                step=0.5, help="Kecepatan angin rata-rata",
            )
            input_data["wind_speed"] = wind_speed
        
        with col_wd:
            wind_direction = st.slider(
                "Arah Angin (°)",
                min_value=0, max_value=360,
                value=_get_int("preset_wind_direction", 45),
                step=5,
                help="0°=Utara, 90°=Timur, 180°=Selatan, 270°=Barat",
            )
            input_data["wind_direction"] = wind_direction
        
        rainfall = st.slider(
            "Curah Hujan 24 Jam (mm)",
            min_value=0.0, max_value=200.0,
            value=_get_float("preset_rainfall", 0.0),
            step=1.0, help="Total curah hujan 24 jam terakhir",
        )
        input_data["rainfall"] = rainfall
    
    st.markdown("---")
    
    # ── What-If Scenario ──────────────────────────────────────────────
    if st.checkbox("✏️ Ubah Manual (What-If Skenario)", key="manual_override"):
        st.markdown('<span class="sim-badge">SIMULASI</span> Sesuaikan parameter untuk simulasi:', unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            override_wind_speed = st.slider(
                "Simulasi Kecepatan Angin (m/s)",
                min_value=0.0, max_value=30.0,
                value=wind_speed, step=0.5, key="override_wind_speed",
            )
            input_data["override_wind_speed"] = override_wind_speed
        with col2:
            override_wind_direction = st.slider(
                "Simulasi Arah Angin (°)",
                min_value=0, max_value=360,
                value=wind_direction, step=5, key="override_wind_direction",
            )
            input_data["override_wind_direction"] = override_wind_direction
        input_data["is_what_if"] = True
    else:
        input_data["is_what_if"] = False
    
    st.markdown("---")
    
    # ── Vegetation / Fuel ─────────────────────────────────────────────
    with st.expander("🌳 Kondisi Bahan Bakar", expanded=True):
        veg_type = st.session_state.get("preset_vegetation_type", "Savana")
        vegetation_type = st.selectbox(
            "Tipe Vegetasi Dominan",
            list(VEGETATION_TYPES.keys()),
            index=list(VEGETATION_TYPES.keys()).index(veg_type) if veg_type in VEGETATION_TYPES else 0,
            help="Pilih tipe vegetasi di lokasi prediksi",
        )
        input_data["vegetation_type"] = vegetation_type
        st.session_state.preset_vegetation_type = vegetation_type
        
        veg_props = VEGETATION_TYPES[vegetation_type]
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            st.metric("Kadar Air Bahan Bakar", f"{veg_props['moisture_content']}%")
        with col_m2:
            st.metric("Indeks Ketercekamannya", f"{veg_props['flammability']:.2f}")
        
        # Auto-set NDVI default when vegetation changes
        last_veg = st.session_state.get("last_vegetation_type")
        if vegetation_type != last_veg:
            st.session_state.preset_ndvi = veg_props["ndvi_default"]
            st.session_state.ndvi_manually_set = False
            st.session_state.last_vegetation_type = vegetation_type
        
        ndvi = st.slider(
            "Indeks NDVI",
            min_value=0.0, max_value=1.0,
            value=_get_float("preset_ndvi", veg_props["ndvi_default"]),
            step=0.01,
            help="Indeks vegetasi (0-1). Berdasarkan tipe vegetasi, harga otomatis diisi.",
        )
        input_data["ndvi"] = ndvi
        st.session_state.preset_ndvi = float(ndvi)
        
        fuel_moisture = st.slider(
            "Kelembaban Bahan Bakar Manual (%)",
            min_value=0, max_value=100,
            value=_get_int("preset_fuel_moisture", veg_props["moisture_content"]),
            step=5, help="Sesuaikan kadar air bahan bakar (0-100%)",
        )
        input_data["fuel_moisture"] = fuel_moisture
    
    st.markdown("---")
    
    # ── Ignition Point ────────────────────────────────────────────────
    with st.expander("🔥 Sumber Kebakaran"):
        st.caption("Masukkan koordinat titik api awal secara manual di bawah.")
        current_data = st.session_state.get("selected_location", {"lat": -1.1747, "lon": 100.4012})
        ignition_lat = st.number_input(
            "Latitude Titik Api",
            value=current_data.get("lat", -1.1747), format="%.4f", key="ignition_lat",
        )
        ignition_lon = st.number_input(
            "Longitude Titik Api",
            value=current_data.get("lon", 100.4012), format="%.4f", key="ignition_lon",
        )
        input_data["ignition_point"] = {"latitude": ignition_lat, "longitude": ignition_lon}
    
    st.markdown("---")
    
    # ── Prediction Time Range ─────────────────────────────────────────
    with st.expander("⏰ Waktu Prediksi", expanded=True):
        prediction_hours = st.slider(
            "Prediksi untuk ... jam ke depan",
            min_value=1, max_value=72, value=12, step=1,
            help="Jangka waktu prediksi (1-72 jam)",
        )
        input_data["prediction_hours"] = prediction_hours
    
    return input_data
