import { getClientBrand } from "../branding";

/** Logo / marca XeniaMAP en la cabecera de paneles laterales. */
export default function BrandHeader({ email }) {
  const brand = getClientBrand(email);
  if (brand.hideLogo) {
    return (
      <div className="brand-title-text" role="img" aria-label={brand.productName}>
        {brand.productName}
      </div>
    );
  }
  return <img className="brand-logo" src={brand.logoSrc} alt={brand.logoAlt} />;
}
