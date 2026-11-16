from era5_tunisia.acquisition.cds_client import create_cds_client

try:
    client = create_cds_client()
    print("CDS Client created successfully!")

except Exception as error:
    print(f"CDS Client creation failed: {error}")

  