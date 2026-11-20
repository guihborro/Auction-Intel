"""Baixa vários anos de ITBI (datasets/itbi_YYYY.xlsx) para ampliar o índice IPTU."""

import os

import requests

URLS = {
    2023: "https://www.prefeitura.sp.gov.br/cidade/secretarias/upload/fazenda/arquivos/XLSX/GUIAS-DE-ITBI-PAGAS-2023.xlsx",
    2022: "https://www.prefeitura.sp.gov.br/cidade/secretarias/upload/fazenda/arquivos/XLSX/GUIAS_DE_ITBI_PAGAS_12-2022.xlsx",
    2021: "https://www.prefeitura.sp.gov.br/cidade/secretarias/upload/fazenda/arquivos/itbi/ITBI_Setembro_2022/GUIAS_DE_ITBI_PAGAS_(2021).xlsx",
    2020: "https://www.prefeitura.sp.gov.br/cidade/secretarias/upload/fazenda/arquivos/itbi/ITBI_Setembro_2022/GUIAS_DE_ITBI_PAGAS_(2020).xlsx",
    2019: "https://www.prefeitura.sp.gov.br/cidade/secretarias/upload/fazenda/arquivos/itbi/ITBI_Setembro_2022/GUIAS_DE_ITBI_PAGAS_(2019).xlsx",
    2018: "https://www.prefeitura.sp.gov.br/cidade/secretarias/upload/fazenda/arquivos/itbi/guias_de_itbi_pagas_2018.xlsx",
    2017: "https://www.prefeitura.sp.gov.br/cidade/secretarias/upload/fazenda/arquivos/itbi/guias_de_itbi_pagas_2017.xlsx",
    2016: "https://www.prefeitura.sp.gov.br/cidade/secretarias/upload/fazenda/arquivos/itbi/guias_de_itbi_pagas_2016.xlsx",
    2015: "https://www.prefeitura.sp.gov.br/cidade/secretarias/upload/fazenda/arquivos/itbi/guias_de_itbi_pagas_2015.xlsx",
}
H = {"User-Agent": "Mozilla/5.0"}


def main() -> None:
    os.makedirs("datasets", exist_ok=True)
    for year, url in URLS.items():
        out = f"datasets/itbi_{year}.xlsx"
        if os.path.exists(out):
            print(f"[skip] {year} já existe", flush=True)
            continue
        try:
            r = requests.get(url, headers=H, timeout=300, stream=True)
            r.raise_for_status()
            n = 0
            with open(out, "wb") as f:
                for c in r.iter_content(1 << 16):
                    f.write(c)
                    n += len(c)
            print(f"[ok] {year}: {n / 1e6:.1f} MB", flush=True)
        except Exception as e:
            print(f"[erro] {year}: {str(e)[:70]}", flush=True)
    print("DOWNLOAD CONCLUIDO.", flush=True)


if __name__ == "__main__":
    main()
