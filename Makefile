.PHONY: deploy

deploy:
	cd web && bash sync_pipeline.sh && npx vercel deploy --prod --yes
