build:
	docker build -t bench-py .

run-model1:
	docker run -i --rm bench-py

run-model2:
	docker run -i --rm bench-py python -u model2.py

clean:
	docker ps -aq --filter "name=bench-" | xargs -r docker rm -f