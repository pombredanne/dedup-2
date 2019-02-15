# run from ubuntu@10.72.102.67

interpreter=~/miniconda3/bin/python

RED='\033[0;31m'
NC='\033[0m'

cd dedup
export PYTHONPATH="$PYTHONPATH:$PWD"
echo $PWD

printf "${RED}dataset\n${NC}"
$interpreter preprocessing/dataset.py \
--data_dir=../data/dedup/ \
--build_features \
--build_tfidf \
--tfidf

# printf "${RED}simboost\n${NC}"
# $interpreter simboost.py \
# --data_dir=../data/dedup/ \
# --tfidf
