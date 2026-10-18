# TeX Live for the lab reports: XeLaTeX with Unicode Computer Modern (CMU) fonts, babel-ukrainian and latexmk
FROM debian:trixie-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        fontconfig \
        fonts-cmu \
        latexmk \
        texlive-fonts-recommended \
        texlive-lang-cyrillic \
        texlive-latex-extra \
        texlive-latex-recommended \
        texlive-xetex \
    && fc-cache -f \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work
