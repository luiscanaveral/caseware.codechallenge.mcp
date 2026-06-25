import argparse
import asyncio
import logging
import os

from mcp.server.models import InitializationOptions

from . import settings

settings.configure_logging()
logger = logging.getLogger("caseware-main")


def run_pipeline():
    from .db.schema import init_db

    os.makedirs(os.path.dirname(settings.DB_PATH) or ".", exist_ok=True)
    os.makedirs(settings.CHROMA_PATH, exist_ok=True)

    logger.info("Initializing database schema...")
    init_db()

    logger.info("Ingesting documents...")
    from .pipeline.ingest import ingest_all
    documents = ingest_all()
    logger.info(f"Ingested {len(documents)} documents.")

    logger.info("Extracting structured data...")
    from .pipeline.extract import extract_all
    extract_all()
    logger.info("Structured extraction complete.")

    logger.info("Generating embeddings and indexing chunks...")
    from .pipeline.embed import embed_all
    embed_all()
    logger.info("Embedding complete.")

    logger.info("Building cross-document references...")
    from .pipeline.index import build_cross_references
    inv_count, ship_count = build_cross_references()
    logger.info(f"Cross-references: {inv_count} invoice-PO, {ship_count} shipment-PO matches.")


async def async_server_main():
    from .server.mcp_server import server
    from mcp.server.stdio import stdio_server
    from mcp.server import NotificationOptions

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name=settings.SERVER_NAME,
                server_version=settings.SERVER_VERSION,
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


def run_server():
    asyncio.run(async_server_main())


def main():
    parser = argparse.ArgumentParser(description="Caseware Procurement Document MCP Server")
    parser.add_argument("--skip-pipeline", action="store_true", help="Skip the ingestion/extraction pipeline")
    parser.add_argument("--pipeline-only", action="store_true", help="Run pipeline only, do not start server")
    args = parser.parse_args()

    if not args.skip_pipeline:
        run_pipeline()
    else:
        logger.info("Skipping pipeline (--skip-pipeline)")

    if args.pipeline_only:
        logger.info("Pipeline complete (--pipeline-only)")
        return

    logger.info("Starting MCP server...")
    run_server()


if __name__ == "__main__":
    main()
