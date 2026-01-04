"""
Cosmos DB 테스트 데이터 정리 스크립트
extraction_logs 컨테이너의 모든 데이터를 삭제합니다.
"""
import os
import sys
from dotenv import load_dotenv

# Load .env from backend
load_dotenv("backend/.env")

from azure.cosmos import CosmosClient

COSMOS_ENDPOINT = os.getenv("COSMOS_ENDPOINT")
COSMOS_KEY = os.getenv("COSMOS_KEY")
COSMOS_DATABASE = os.getenv("COSMOS_DATABASE", "daom")

def main():
    if not COSMOS_ENDPOINT or not COSMOS_KEY:
        print("❌ COSMOS_ENDPOINT 또는 COSMOS_KEY가 설정되지 않았습니다.")
        print("backend/.env 파일을 확인해주세요.")
        sys.exit(1)
    
    print(f"🔗 Cosmos DB 연결 중...")
    print(f"   Endpoint: {COSMOS_ENDPOINT}")
    print(f"   Database: {COSMOS_DATABASE}")
    
    client = CosmosClient(COSMOS_ENDPOINT, COSMOS_KEY)
    database = client.get_database_client(COSMOS_DATABASE)
    
    # List all containers
    containers = list(database.list_containers())
    print(f"\n📦 사용 가능한 컨테이너:")
    for c in containers:
        print(f"   - {c['id']}")
    
    # Check ExtractedData container (extraction logs)
    try:
        logs_container = database.get_container_client("ExtractedData")
        
        # Count items
        query = "SELECT VALUE COUNT(1) FROM c"
        count = list(logs_container.query_items(query, enable_cross_partition_query=True))[0]
        print(f"\n📊 extraction_logs 컨테이너: {count}개 항목")
        
        if count == 0:
            print("✅ 이미 비어있습니다!")
            return
        
        # Ask for confirmation
        confirm = input(f"\n⚠️  {count}개 항목을 모두 삭제하시겠습니까? (yes/no): ")
        if confirm.lower() != 'yes':
            print("🚫 취소되었습니다.")
            return
        
        # Delete all items
        print("\n🗑️  삭제 중...")
        items = list(logs_container.query_items("SELECT c.id, c.model_id FROM c", enable_cross_partition_query=True))
        
        deleted = 0
        for item in items:
            try:
                # Use model_id as partition key
                partition_key = item.get('model_id', item['id'])
                logs_container.delete_item(item['id'], partition_key=partition_key)
                deleted += 1
                if deleted % 10 == 0:
                    print(f"   {deleted}/{len(items)} 삭제됨...")
            except Exception as e:
                print(f"   ❌ 삭제 실패 (id={item['id']}): {e}")
        
        print(f"\n✅ 완료! {deleted}개 항목이 삭제되었습니다.")
        
    except Exception as e:
        print(f"❌ 오류: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
