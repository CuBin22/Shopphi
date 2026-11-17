from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from lxml import etree as E
from PIL import Image, ImageDraw, ImageFont
import io, shutil, json

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'BaoCao_Shopphi_TruongKienPhi.docx'
OUT = ROOT / 'backups' / 'report_update_20261113'
OUT.mkdir(parents=True, exist_ok=True)
BACKUP = OUT / SOURCE.name
if not BACKUP.exists(): shutil.copy2(SOURCE, BACKUP)
NS = {'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main', 'a':'http://schemas.openxmlformats.org/drawingml/2006/main', 'r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships', 'wp':'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'}
with ZipFile(BACKUP) as z: parts = {n:z.read(n) for n in z.namelist()}
doc = E.fromstring(parts['word/document.xml'])
ps = doc.find('w:body',NS).findall('w:p',NS)
rels = E.fromstring(parts['word/_rels/document.xml.rels'])
targets = {r.get('Id'):'word/'+r.get('Target') for r in rels}
updates = {
620:'Về tổ chức vận hành, Shopphi gồm ba nhóm người dùng: Quản trị viên, Người bán và Khách hàng. Quản trị viên quản lý hoạt động toàn sàn, xét duyệt gian hàng và kiểm soát nội dung. Người bán quản lý gian hàng, sản phẩm, tồn kho, mã giảm giá và đơn hàng thuộc phạm vi được phân quyền. Khách hàng tìm kiếm sản phẩm, đặt hàng, thanh toán, theo dõi giao hàng và đánh giá sản phẩm. Hình 2.1 trình bày sự phân công chức năng giữa các nhóm người dùng; kiến trúc phần mềm được trình bày riêng tại mục 3.1.1.',
621:'Các nhóm người dùng phối hợp thông qua quy trình xử lý thống nhất trên hệ thống. Đơn hàng được tách theo gian hàng để mỗi Người bán xử lý phần hàng thuộc trách nhiệm của mình. Quản trị viên thực hiện các nghiệp vụ quản lý toàn sàn và xác nhận hoàn tiền theo thẩm quyền. Dịch vụ thanh toán, giao vận, gửi mã OTP và tư vấn tự động hỗ trợ quy trình này thông qua các kết nối do máy chủ kiểm soát.',
1184:'Shopphi được xây dựng theo kiến trúc nguyên khối có phân mô-đun (modular monolith). Ứng dụng Django gồm bốn mô-đun accounts, catalog, shopping và chatbot, sử dụng chung cơ sở dữ liệu PostgreSQL. Giao diện được kết xuất bằng Django Template kết hợp JavaScript; các yêu cầu nghiệp vụ được xử lý tại máy chủ và truy cập dữ liệu thông qua Django ORM. Cách tổ chức này phù hợp với phạm vi đồ án và được lựa chọn dựa trên các yếu tố sau:',
1185:'Tính nhất quán dữ liệu. Các thay đổi liên quan đến đơn hàng, tồn kho và lượt sử dụng mã giảm giá được thực hiện trong giao dịch cơ sở dữ liệu, kết hợp khóa dòng và cập nhật có điều kiện. Giao dịch với cổng thanh toán hoặc đơn vị vận chuyển là tương tác bên ngoài; hệ thống cần xác thực, đối soát và xử lý phản hồi lặp thay vì xem các lời gọi API là một phần của giao dịch ACID trong PostgreSQL.',
1186:'Khả năng triển khai. Cấu hình Docker Compose tổ chức ứng dụng web và cơ sở dữ liệu thành các dịch vụ riêng. Dịch vụ email, cổng thanh toán, GHN và mô hình ngôn ngữ được kết nối qua cấu hình môi trường. Các tác vụ xử lý hết hạn và đồng bộ giao vận cần được gọi định kỳ để duy trì trạng thái nghiệp vụ.',
1187:'Khả năng bảo trì. Bốn mô-đun phân chia trách nhiệm theo nhóm chức năng, trong khi các hàm dịch vụ tập trung những quy tắc dùng chung. Gợi ý sản phẩm và chatbot hiện được xử lý trong ứng dụng Django; việc tách thành dịch vụ độc lập chỉ là hướng mở rộng khi có yêu cầu về tải và vận hành.',
1197:'Bộ phận gợi ý sản phẩm được hiện thực bằng các hàm nghiệp vụ trong ứng dụng catalog, không phải một dịch vụ triển khai độc lập. Yêu cầu từ trình duyệt được chuyển đến view của Django; hệ thống khai thác dữ liệu hành vi và thông tin sản phẩm trong PostgreSQL để tạo danh sách gợi ý, sau đó trả kết quả cho giao diện. Dữ liệu trung gian được lưu đệm nhằm giảm chi phí tính toán trong các yêu cầu tiếp theo.',
1216:'Quy trình đặt hàng được tập trung tại hàm place_order của ứng dụng shopping. Hệ thống tiếp nhận danh sách biến thể và số lượng từ giỏ hàng hoặc thao tác Mua ngay, tạo một nhóm đơn cho lần đặt hàng và một đơn riêng cho mỗi gian hàng. Các bước xử lý chính gồm:',
1218:'Trong giao dịch cơ sở dữ liệu, hệ thống khóa các biến thể theo thứ tự khóa chính, kiểm tra trạng thái kinh doanh của sản phẩm và gian hàng, đồng thời đối chiếu số lượng mua với tồn kho khả dụng.',
1219:'Các dòng hàng được nhóm theo gian hàng để tính tiền, áp mã giảm giá và phân bổ khoản giảm giá toàn sàn. Khi bật GHN, hệ thống tính lại cước theo thông tin giao nhận; nếu tổng tiền khác mức khách đã xác nhận, yêu cầu đặt hàng bị từ chối để khách tính lại phí.',
1225:'Đơn hàng có các trạng thái xử lý chính gồm Chờ xác nhận, Đã xác nhận, Đang giao và Hoàn thành; các nhánh ngoại lệ gồm Đã hủy và Giao thất bại. Với giao hàng thủ công, Người bán chuyển trạng thái theo thứ tự và nhập mã vận đơn khi giao hàng. Với đơn GHN, thao tác xác nhận gắn với việc tạo vận đơn; trạng thái giao nhận được cập nhật từ đơn vị vận chuyển. Đơn thanh toán trực tuyến chỉ được xác nhận sau khi thanh toán thành công.',
1228:'Các thao tác chuyển trạng thái ghi nhận nhật ký để phục vụ theo dõi và đối soát. Đơn giao hàng thủ công được hoàn thành khi khách xác nhận đã nhận hàng hoặc tác vụ định kỳ xử lý sau thời hạn quy định. Đơn GHN chỉ hoàn thành khi GHN xác nhận giao thành công; quy tắc tự hoàn thành sau bảy ngày không áp dụng cho nhóm đơn này. Khi hoàn thành đơn COD, hệ thống đồng thời ghi nhận trạng thái đã thanh toán.',
998:'Các sơ đồ hoạt động từ Hình 2.15 đến Hình 2.36 mô tả 22 quy trình nghiệp vụ. Mỗi sơ đồ thể hiện luồng xử lý chính và điều kiện kiểm soát tương ứng. Đối với đặt hàng, thanh toán, hủy đơn và giao nhận, hệ thống kiểm tra quyền truy cập, trạng thái hiện tại và kết quả xử lý trước khi cập nhật dữ liệu. Nhánh lỗi kết thúc yêu cầu hiện tại và cho phép người dùng thực hiện lại sau khi điều chỉnh dữ liệu.',
1412:'Về thanh toán và giao vận, hệ thống có các thành phần tích hợp VNPay, cổng giả lập và GHN. Các cơ chế giữ kho, xác thực phản hồi, đối chiếu số tiền, xử lý kết quả lặp và ghi nhận thanh toán muộn hỗ trợ kiểm soát tính nhất quán. Mức độ ổn định khi vận hành thực tế cần tiếp tục được đánh giá bằng kiểm thử tích hợp và đối soát với nhà cung cấp.',
1417:'Về khả năng ứng dụng, hệ thống cung cấp nền tảng thử nghiệm cho mô hình kinh doanh đa gian hàng, tập trung dữ liệu sản phẩm, tồn kho và đơn hàng trên một ứng dụng. Hiệu quả giảm thao tác thủ công và cải thiện trải nghiệm mua sắm cần được đánh giá thêm với người dùng thực tế trước khi triển khai rộng rãi.',
1430:'Hoàn thiện chatbot bằng cách đánh giá chất lượng truy xuất lai và câu trả lời trên bộ câu hỏi nghiệp vụ, mở rộng khả năng sử dụng ngữ cảnh hội thoại, đồng thời đo độ trễ và chi phí gọi API. Cần bổ sung các tình huống kiểm thử về dữ liệu thiếu, sản phẩm ngừng bán và truy vấn đơn hàng để kiểm soát phạm vi thông tin được cung cấp.'
}
for i,text in updates.items():
    nodes=ps[i].findall('.//w:t',NS)
    assert nodes, i
    # Preserve every run and paragraph property; distribute text across existing runs.
    cursor=0
    for j,n in enumerate(nodes):
        count=len(n.text or '') if j<len(nodes)-1 else len(text)-cursor
        n.text=text[cursor:cursor+count]; cursor+=count
        n.set('{http://www.w3.org/XML/1998/namespace}space','preserve')

fontpath='C:/Windows/Fonts/arial.ttf'
def diagram(steps, branches=None):
    branches=branches or {}
    im=Image.new('RGB',(1800,1100),'white'); d=ImageDraw.Draw(im)
    f=ImageFont.truetype(fontpath,30)
    def text_box(rect,text):
        x,y,x2,y2=rect; d.rounded_rectangle(rect,12,outline='black',width=3)
        lines=[]
        for para in text.split('\n'):
            line=''
            for word in para.split():
                trial=(line+' '+word).strip()
                if d.textlength(trial,font=f)>x2-x-35: lines.append(line); line=word
                else: line=trial
            lines.append(line)
        assert len(lines)*37<=y2-y-8, text
        for k,line in enumerate(lines): d.text(((x+x2-d.textlength(line,font=f))/2,(y+y2-len(lines)*37)/2+k*37),line,font=f,fill='black')
    def arrow(x,y,x2,y2):
        d.line((x,y,x2,y2),fill='black',width=3)
        if x==x2:d.polygon([(x2,y2),(x2-8,y2-14),(x2+8,y2-14)],fill='black')
        else:d.polygon([(x2,y2),(x2-14,y2-8),(x2-14,y2+8)],fill='black')
    h=120; gap=(1000-len(steps)*h)/max(1,len(steps)-1)
    for k,s in enumerate(steps):
        y=45+k*(h+gap); text_box((70,y,1120,y+h),s)
        if k: arrow(595,y-gap,595,y)
        if k in branches:
            arrow(1120,y+h/2,1210,y+h/2); text_box((1210,y,1760,y+h),branches[k])
    return im

flows=[
(['Nhập Gmail, mật khẩu và thông tin đăng ký','Kiểm tra dữ liệu; gửi OTP và lưu thông tin tạm trong phiên','Nhập OTP; kiểm tra hiệu lực và số lần thử','Tạo tài khoản và hồ sơ trong giao dịch dữ liệu','Thông báo đăng ký thành công; chuyển đến đăng nhập'],{2:'OTP sai hoặc hết hạn: báo lỗi, cho phép gửi lại theo giới hạn'}),
(['Nhập thông tin đăng nhập','Kiểm tra tài khoản, mật khẩu và trạng thái khóa','Xác thực thành công; thiết lập phiên đăng nhập','Hợp nhất dữ liệu khách vãng lai theo quy tắc hệ thống','Chuyển đến giao diện phù hợp với vai trò'],{1:'Không hợp lệ: báo lỗi; áp dụng giới hạn đăng nhập sai'}),
(['Nhập từ khóa và điều kiện lọc','Chuẩn hóa dữ liệu truy vấn','Tìm sản phẩm đang hiển thị trong gian hàng hoạt động','Áp dụng bộ lọc, sắp xếp và phân trang','Hiển thị kết quả và ghi nhận hành vi tìm kiếm'],{3:'Không có kết quả: hiển thị thông báo phù hợp'}),
(['Người dùng mở trang có gợi ý','Lấy lịch sử hành vi và tập sản phẩm hợp lệ','Tính điểm gợi ý dựa trên dữ liệu tương tác','Kết hợp hoặc bổ sung kết quả dự phòng','Loại kết quả trùng; trả danh sách sản phẩm'],{2:'Thiếu dữ liệu: sử dụng phương án gợi ý dự phòng'}),
(['Chọn biến thể và số lượng','Kiểm tra trạng thái sản phẩm, gian hàng và tồn kho','Thêm hoặc cập nhật dòng giỏ hàng','Lưu giỏ trong phiên hoặc cơ sở dữ liệu theo đăng nhập','Hiển thị giỏ hàng và tổng tiền tạm tính'],{1:'Không hợp lệ: báo lỗi, không thêm hàng'}),
(['Chọn hàng; nhập địa chỉ, mã giảm giá và cách thanh toán','Khóa biến thể; kiểm tra hàng, tồn kho và mã giảm giá','Tính tiền và cước; đối chiếu mức phí GHN nếu được bật','Tạo nhóm đơn; tách đơn theo gian hàng; trừ tồn kho','Ghi lượt dùng mã, nhật ký và thông báo; hoàn tất đặt hàng'],{2:'Dữ liệu hoặc phí thay đổi: hủy giao dịch, yêu cầu xác nhận lại',4:'Trực tuyến: giữ kho theo hạn; Mua ngay: giữ nguyên giỏ'}),
(['Tạo giao dịch thanh toán cho phần đơn hợp lệ','Chuyển khách đến cổng thanh toán','Nhận phản hồi hoặc chủ động truy vấn kết quả','Xác thực chữ ký, mã giao dịch, số tiền và trạng thái','Áp dụng kết quả hợp lệ một lần; cập nhật trạng thái thanh toán'],{3:'Sai dữ liệu: từ chối cập nhật',4:'Thanh toán muộn: ghi nhận để đối soát và hoàn tiền'}),
(['Khách hàng mở danh sách hoặc chi tiết đơn','Kiểm tra đăng nhập và quyền sở hữu đơn','Truy xuất trạng thái, thanh toán và lịch sử xử lý','Hiển thị mã vận đơn và thông tin giao nhận','Cho phép thao tác phù hợp với trạng thái hiện tại'],{1:'Không có quyền: từ chối truy cập'}),
(['Khách yêu cầu xác nhận đã nhận hàng','Kiểm tra quyền sở hữu và trạng thái giao nhận','Đơn thủ công: yêu cầu trạng thái Đang giao','Đơn GHN: yêu cầu GHN xác nhận delivered','Hoàn thành đơn; ghi nhận COD, hành vi mua và nhật ký'],{3:'GHN chưa giao thành công: từ chối hoàn thành'}),
(['Khách nhập lý do hủy; hệ thống kiểm tra quyền','Chờ xác nhận: hủy ngay; Đã xác nhận: tạo yêu cầu hủy','Người bán xử lý yêu cầu; tác vụ xét yêu cầu quá hạn','Kiểm tra khả năng hủy vận đơn GHN nếu có','Hủy đơn; hoàn kho và lượt mã theo quy tắc; ghi nhật ký'],{1:'Đang giao hoặc đã hoàn thành: không cho hủy',4:'Đã thanh toán: chuyển sang Chờ hoàn tiền'}),
(['Tiếp nhận câu hỏi; kiểm tra độ dài và tần suất','Chuẩn hóa câu hỏi; che dữ liệu cá nhân','Nhận diện ý định; truy xuất sản phẩm hoặc đơn được phép xem','Tạo ngữ cảnh từ dữ liệu và hướng dẫn nghiệp vụ','Gọi mô hình; trả lời và lưu lịch sử hội thoại'],{4:'Thiếu khóa hoặc lỗi dịch vụ: phản hồi bằng cơ chế dự phòng'}),
(['Người bán nhập thông tin gian hàng','Kiểm tra vai trò, dữ liệu và điều kiện đăng ký','Lưu hồ sơ gian hàng ở trạng thái chờ duyệt','Quản trị viên xem xét hồ sơ','Duyệt để hoạt động hoặc từ chối kèm lý do'],{}),
(['Người bán mở quản lý sản phẩm','Kiểm tra quyền trên gian hàng và sản phẩm','Nhập sản phẩm, danh mục, biến thể, giá, kho và ảnh','Kiểm tra dữ liệu và xử lý ảnh tải lên','Lưu thay đổi; cập nhật danh sách sản phẩm'],{3:'Dữ liệu không hợp lệ: hiển thị lỗi để sửa'}),
(['Mở chức năng quản lý mã giảm giá','Xác định phạm vi toàn sàn hoặc gian hàng theo quyền','Nhập điều kiện, thời hạn và mức giảm','Kiểm tra tính hợp lệ và tình trạng sử dụng mã','Lưu mới hoặc cập nhật theo giới hạn nghiệp vụ'],{3:'Mã đã dùng: hạn chế sửa, không xóa tùy ý'}),
(['Người bán yêu cầu cập nhật đơn','Kiểm tra quyền, trạng thái và thanh toán trực tuyến','Đơn GHN: xác nhận tạo vận đơn, đồng bộ từ hãng','Đơn thủ công: chuyển tuần tự và nhập mã khi giao','Ghi trạng thái, nhật ký và thông báo'],{2:'Kết quả tạo vận đơn chưa rõ: đối soát trước khi xử lý tiếp',3:'Yêu cầu hủy chưa giải quyết: chặn chuyển giao'}),
(['Quản trị viên mở hồ sơ gian hàng chờ duyệt','Kiểm tra thông tin và trạng thái hồ sơ','Chọn chấp thuận hoặc từ chối','Cập nhật trạng thái; ghi lý do khi từ chối','Ghi nhật ký và thông báo cho Người bán'],{}),
(['Quản trị viên chọn sản phẩm hoặc gian hàng','Kiểm tra quyền và trạng thái hiện tại','Chọn gỡ, khôi phục, khóa hoặc mở khóa','Kiểm tra lý do và điều kiện của thao tác','Cập nhật dữ liệu; ghi nhật ký và thông báo'],{}),
(['Quản trị viên mở từ điển từ khóa','Nhập mới hoặc chọn từ khóa cần quản lý','Chuẩn hóa từ khóa và kiểm tra trùng','Cập nhật nội dung hoặc trạng thái hiển thị','Lưu dữ liệu phục vụ gợi ý tìm kiếm'],{}),
(['Người dùng quản lý chọn kỳ thống kê','Kiểm tra quyền và khoảng thời gian','Giới hạn dữ liệu theo gian hàng hoặc toàn sàn','Tổng hợp các chỉ số theo quy tắc báo cáo','Hiển thị thống kê và danh sách liên quan'],{}),
(['Người dùng mở danh sách thông báo','Kiểm tra phiên đăng nhập','Truy vấn thông báo thuộc người dùng hiện tại','Hiển thị nội dung và trạng thái đã đọc','Đánh dấu đã đọc hoặc mở liên kết nội bộ hợp lệ'],{}),
(['Khách chọn sản phẩm trong đơn đã hoàn thành','Kiểm tra quyền mua hàng và điều kiện đánh giá','Nhập số sao và nội dung nhận xét','Kiểm tra số sao và đánh giá đã tồn tại','Lưu đánh giá và hiển thị kết quả'],{3:'Không đủ điều kiện hoặc dữ liệu sai: từ chối lưu'}),
(['Quản trị viên chọn giao dịch cần hoàn tiền','Kiểm tra quyền và trạng thái chờ hoàn','Thực hiện hoàn theo nhà cung cấp hoặc chế độ mô phỏng','Kiểm tra kết quả; không xác nhận khi hoàn thất bại','Lưu bản ghi hoàn tiền và cập nhật trạng thái'],{})
]
images={622:Image.open(ROOT/'so_do_to_chuc_shopphi_thiet_ke_lai.png')}
images[1194]=diagram(['Trình duyệt: Django Template, CSS và JavaScript','Máy chủ Django: định tuyến, xác thực và phân quyền','accounts: tài khoản | catalog: danh mục, sản phẩm và gợi ý','shopping: giỏ, đơn, thanh toán, giao vận | chatbot: tư vấn','Django ORM và PostgreSQL; tệp ảnh tại vùng lưu trữ media'],{1:'Email OTP: SMTP hoặc Brevo theo cấu hình',3:'API ngoài: VNPay, GHN và Gemini'})
for k,(steps,branches) in enumerate(flows): images[999+2*k]=diagram(steps,branches)
for i,im in images.items():
    blip=ps[i].find('.//a:blip',NS); assert blip is not None,i
    target=targets[blip.get('{'+NS['r']+'}embed')]
    extent=ps[i].find('.//wp:extent',NS)
    ratio=int(extent.get('cx'))/int(extent.get('cy'))
    # Retain the original physical dimensions and fit without stretching.
    w=2400; h=round(w/ratio)
    canvas=Image.new('RGB',(w,h),'white')
    im=im.convert('RGB'); im.thumbnail((w,h),Image.Resampling.LANCZOS)
    canvas.paste(im,((w-im.width)//2,(h-im.height)//2))
    b=io.BytesIO(); canvas.save(b,format='PNG'); parts[target]=b.getvalue()
    canvas.save(OUT/f'diagram_{i}.png')
parts['word/document.xml']=E.tostring(doc,xml_declaration=True,encoding='UTF-8',standalone=True)
candidate=OUT/'updated.docx'
with ZipFile(candidate,'w',ZIP_DEFLATED) as z:
    for n,data in parts.items(): z.writestr(n,data)
# Validate preserved formatting and package integrity before replacing the target.
with ZipFile(BACKUP) as z: old=E.fromstring(z.read('word/document.xml'))
for xpath in ['.//w:pPr','.//w:rPr','.//w:sectPr','.//wp:extent']:
    assert [E.tostring(x) for x in old.findall(xpath,NS)]==[E.tostring(x) for x in doc.findall(xpath,NS)],xpath
with ZipFile(candidate) as z: assert z.testzip() is None
shutil.copy2(candidate,SOURCE)
(OUT/'changes.json').write_text(json.dumps({'paragraphs':list(updates),'diagrams':list(images),'backup':str(BACKUP)},ensure_ascii=False,indent=2),encoding='utf-8')
print(f'Updated {len(updates)} paragraphs and {len(images)} diagrams; formatting properties preserved.')
